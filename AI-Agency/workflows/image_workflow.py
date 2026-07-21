# /var/www/teknovia/AI-Agency/workflows/image_workflow.py
import os
import io
import base64
import logging
import requests
import mimetypes
import re
import urllib.parse
import concurrent.futures
import time
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, SecretStr

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_deepseek import ChatDeepSeek

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.db import transaction
from accounts.models import ApiContainer
from contents.models import Content, MediaContainer, PostsContainer
from workflows.logging_services import add_log_event

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# ساختارهای وضعیت Pydantic (Pydantic Workflow States)
# ────────────────────────────────────────────────────────────────

class ImageWorkflowState(BaseModel):
    tracking_id: str = Field(..., description="شناسه عددی یکتا و جهانی (UUID) برای ردیابی این پیشنهاد تصویری.")
    prompt: str = Field(..., description="شرح دقیق یا پرامپت تعریف شده برای تصویر پیشنهادی.")
    placements: List[str] = Field(default_factory=list, description="محل‌های قرارگیری تصویر در خروجی‌ها.")
    inline_position: Optional[str] = Field(None, description="محل قرارگیری دقیق بین‌متنی تصویر.")
    local_id: int = Field(..., description="شناسه محلی عددی ترتیبی در متن مقاله.")
    message_id: int = Field(..., description="شناسه پیام دریافتی تلگرام مرجع جهت ثبت لاگ‌ها.")

    # متغیرهای وضعیت داخلی ورک‌فلو
    supervisor_decision: str = Field(default="")  # "generate" or "find"
    search_queries: List[str] = Field(default_factory=list)
    found_urls: List[str] = Field(default_factory=list)
    selected_image_url: Optional[str] = Field(default=None)
    selected_image_bytes: Optional[bytes] = Field(default=None)
    fallback_prompt: Optional[str] = Field(default=None)
    generated_alt_text: Optional[str] = Field(default=None)  # Alt text جدید در صورت سوئیچ به تولید تصویر

    # مرجع خروجی ذخیره شده
    media_id: Optional[int] = Field(default=None)


# ────────────────────────────────────────────────────────────────
# الگوهای ساختار یافته خروجی مدل (LLM Structured Schemas)
# ────────────────────────────────────────────────────────────────

class ImageSupervisorDecision(BaseModel):
    decision: Literal["generate", "find"] = Field(
        ...,
        description="Select 'find' if the incoming prompt explicitly recommends searching the internet or refers to a real-world company, product, or branding. Select 'generate' if it is a pure artistic prompt for image generation."
    )
    queries: List[str] = Field(
        default_factory=list,
        description="If decision is 'find', provide 1 to 3 simplified, extremely short keyword-based search queries. Keep queries under 4 words."
    )


class GeminiImageSelection(BaseModel):
    has_match: bool = Field(
        ...,
        description="True if one of the candidate images downloaded is a perfect, genuine and high-quality match. False otherwise."
    )
    selected_index: Optional[int] = Field(
        None,
        description="The index of the selected candidate image (starting from 1) if has_match is True."
    )
    fallback_prompt: Optional[str] = Field(
        None,
        description="If has_match is False, write a highly descriptive, detailed prompt in English for a text-to-image AI model."
    )
    generated_alt_text: Optional[str] = Field(
        None,
        description="If has_match is False, you MUST write a new, gorgeous, SEO-friendly Persian alt text (under 100 characters) accurately describing the abstract/conceptual scene that will be generated."
    )
    reason: str = Field(
        ...,
        description="Provide a clear, detailed explanation of your decision in Persian."
    )


# ────────────────────────────────────────────────────────────────
# توابع فشرده‌سازی هوشمند تصاویر
# ────────────────────────────────────────────────────────────────

def compress_image_bytes(img_bytes: bytes, max_dim: int = 800, quality: int = 70) -> Optional[bytes]:
    """فشرده‌ساز سبک برای پکت‌های ورودی به مدل بینایی جمینای"""
    try:
        img = Image.open(io.BytesIO(img_bytes))

        if img.mode == "P":
            if "transparency" in img.info:
                img = img.convert("RGBA")

        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        width, height = img.size

        if width > max_dim or height > max_dim:
            if width > height:
                new_width = max_dim
                new_height = int(height * (max_dim / width))
            else:
                new_height = max_dim
                new_width = int(width * (max_dim / height))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", quality=quality, optimize=True)
        return out_io.getvalue()

    except Exception as e:
        logger.warning(f"Failed to compress image bytes dynamically: {e}")
        return None


def compress_image_smart(img_bytes: bytes, max_dim: int = 1200, quality: int = 85) -> bytes:
    """فشرده‌ساز هوشمند تصاویر برای استاندارد وب"""
    try:
        original_size_kb = len(img_bytes) / 1024
        img = Image.open(io.BytesIO(img_bytes))

        if img.mode == "P":
            if "transparency" in img.info:
                img = img.convert("RGBA")

        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        width, height = img.size

        if original_size_kb < 250 and max(width, height) <= max_dim:
            return img_bytes

        if width > max_dim or height > max_dim:
            if width > height:
                new_width = max_dim
                new_height = int(height * (max_dim / width))
            else:
                new_height = max_dim
                new_width = int(width * (max_dim / height))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", quality=quality, optimize=True)
        return out_io.getvalue()

    except Exception as e:
        logger.warning(f"Error in smart image compressor: {e}")
        return img_bytes


# ────────────────────────────────────────────────────────────────
# متد کمکی فوق‌العاده منعطف و باکیفیت به عنوان فال‌بک پیشرفته پروداکشن
# ────────────────────────────────────────────────────────────────

def get_high_quality_production_fallback(state: ImageWorkflowState, prompt: str) -> Dict[str, Any]:
    """
    جایگزین نهایی بسیار باکیفیت برای پروداکشن (منسوخ کردن فال‌بک Pillow):
    ۱. تلاش برای تولید عکس زنده و بسیار زیبا به کمک API رایگان و بدون محدودیت Pollinations.ai
    ۲. در صورت خطای شبکه، دانلود یک تصویر استاتیک آبستره فناوری از Unsplash جهت تضمین سلامت بصری
    """
    logger.info("اجرای مکانیسم فال‌بک پیشرفته پروداکشن برای تولید تصویر...")
    add_log_event(state.message_id, "IMAGE_FALLBACK_TRIGGERED", 
                  "سرویس deAPI با خطا مواجه شد. در حال تولید تصویر هنری باکیفیت از لایه موازی کمکی...")

    # ۱. تلاش برای استفاده از Pollinations AI (تولید عکس واقعی با موتور FLUX بدون نیاز به کلید)
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        pollinations_url = f"https://image.pollinations.ai/p/{encoded_prompt}?width=1024&height=768&nologo=true&seed={state.local_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(pollinations_url, headers=headers, timeout=20)
        if res.status_code == 200 and len(res.content) > 5000:
            add_log_event(state.message_id, "IMAGE_FALLBACK_POLLINATIONS_SUCCESS", 
                          "تصویر هنری باکیفیت با موفقیت توسط موتور کمکی Pollinations تولید و دانلود شد.")
            return {
                "selected_image_url": pollinations_url,
                "selected_image_bytes": res.content
            }
    except Exception as e:
        logger.warning(f"Pollinations.ai fallback failed: {e}")

    # ۲. لایه نهایی حفاظت (دانلود تصویر استاتیک فناوری فوق‌العاده باکیفیت از Unsplash به جای Pillow متنی قدیمی)
    fallback_unsplash_urls = [
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1639762681485-074b7f938ba0?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1635070041078-e363dbe005cb?auto=format&fit=crop&w=1200&q=80"
    ]
    
    selected_unsplash_url = fallback_unsplash_urls[state.local_id % len(fallback_unsplash_urls)]
    add_log_event(state.message_id, "IMAGE_FALLBACK_UNSPLASH", 
                  "دانلود تصویر استاتیک فناوری از سرورهای Unsplash به عنوان لایه حفاظت نهایی...")

    try:
        res = requests.get(selected_unsplash_url, timeout=15)
        if res.status_code == 200:
            return {
                "selected_image_url": selected_unsplash_url,
                "selected_image_bytes": res.content
            }
    except Exception as e:
        logger.error(f"Unsplash fallback download failed: {e}")

    # ۳. بازگرداندن آدرس معتبر نهایی در بدترین سناریو ممکن جهت جلوگیری از خراب شدن طرح صفحات
    return {
        "selected_image_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
        "selected_image_bytes": b""
    }


# ────────────────────────────────────────────────────────────────
# پیاده‌سازی گام‌به‌گام نودها (Nodes Implementation)
# ────────────────────────────────────────────────────────────────

def image_supervisor_node(state: ImageWorkflowState) -> Dict[str, Any]:
    """نود ناظر تصویر: تصمیم‌گیری بین جستجوی وب یا تولید مستقیم"""
    logger.info(f"شروع ارزیابی سوپروایزر تصویر برای پیشنهاد {state.tracking_id}...")
    add_log_event(state.message_id, "IMAGE_SUPERVISOR_START",
                  f"بررسی مسیر آماده‌سازی تصویر پیشنهادی با شناسه محلی {state.local_id}...")

    api = ApiContainer.objects.filter(status=True, provider="deepseek").order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("DEEPSEEK_API_KEY")

    decision = "generate"
    queries = []

    if api_key:
        try:
            llm = ChatDeepSeek(
                api_key=SecretStr(api_key),
                model="deepseek-v4-flash",
                temperature=0.1,
                extra_body={"thinking": {"type": "disabled"}}
            ).with_structured_output(ImageSupervisorDecision)

            system_instruction = (
                "You are an elite, minimal search coordinator.\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. If the incoming text contains 'Better search this image on the internet', decision MUST be 'find'. Extrapolate and simplify the queries.\n"
                "2. EVERY QUERY MUST BE CONCISE (maximum 3-4 words, e.g. 'Nvidia Blackwell chip', 'Anthropic Claude logo').\n"
                "3. NEVER use descriptive details, lighting instructions, render styles, or camera angles in search queries. Keep it strictly focused on the core product/logo/person."
            )

            response = llm.invoke([
                SystemMessage(content=system_instruction),
                HumanMessage(content=f"Requested Image Prompt/Description: {state.prompt}")
            ])

            decision = response.decision
            queries = response.queries

            if api:
                try:
                    api.increment_usage()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error in image_supervisor_node LLM: {e}")
            add_log_event(state.message_id, "IMAGE_SUPERVISOR_ERROR",
                          f"خطا در مدل تصمیم‌گیری سوپروایزر تصویر: {str(e)}")
    else:
        logger.warning("No DeepSeek API Key found for image supervisor. Defaulting to 'generate'.")

    add_log_event(
        state.message_id,
        "IMAGE_SUPERVISOR_DECISION",
        f"تصمیم سوپروایزر تصویر: {decision} | تعداد کوئری‌های تولید شده: {len(queries)}",
        {"decision": decision, "queries": queries}
    )

    return {
        "supervisor_decision": decision,
        "search_queries": queries
    }


def supervisor_routing(state: ImageWorkflowState) -> Literal["finder", "generator"]:
    if state.supervisor_decision == "find":
        return "finder"
    return "generator"


def download_single_image_bytes(url: str, timeout: int = 5) -> Optional[bytes]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=timeout)
        if res.status_code == 200:
            content_type = res.headers.get("Content-Type", "")
            if "image" in content_type:
                return res.content
    except Exception:
        pass
    return None


def image_finder_node(state: ImageWorkflowState) -> Dict[str, Any]:
    """نود جستجوگر تصویر: واکشی از سرپر، دانلود موازی و گزینش توسط جمینای"""
    logger.info("اجرای نود جستجوگر تصویر در وب...")
    add_log_event(state.message_id, "IMAGE_FINDER_START", f"در حال آغاز فرآیند جستجوی گوگل برای کوئری‌ها...")

    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        logger.error("SERPER_API_KEY is not configured.")
        add_log_event(state.message_id, "IMAGE_FINDER_ERROR",
                      "کلید سرور Serper API تنظیم نشده است. انتقال به تولید تصویر.")
        return {"supervisor_decision": "generate"}

    all_candidate_urls = []

    for q in state.search_queries[:5]:
        url = "https://google.serper.dev/images"
        headers = {
            "X-API-KEY": serper_key,
            "Content-Type": "application/json"
        }
        payload = {"q": q, "num": 6}
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=8)
            if res.status_code == 200:
                data = res.json()
                images = data.get("images", [])
                for img in images[:6]:
                    img_url = img.get("imageUrl")
                    if img_url and img_url not in all_candidate_urls:
                        all_candidate_urls.append(img_url)
        except Exception as e:
            logger.error(f"Serper API Request failed for query '{q}': {e}")

    all_candidate_urls = all_candidate_urls[:18]

    if not all_candidate_urls:
        add_log_event(state.message_id, "IMAGE_FINDER_NO_URLS",
                      "هیچ آدرس عکسی در نتایج جستجو یافت نشد. انتقال به تولید تصویر.")
        return {"supervisor_decision": "generate"}

    add_log_event(state.message_id, "IMAGE_FINDER_DOWNLOADING",
                  f"تعداد {len(all_candidate_urls)} آدرس کاندید یافت شد. دانلود و فشرده‌سازی موازی...")

    downloaded_data: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(download_single_image_bytes, url): url for url in all_candidate_urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                img_bytes = future.result()
                if img_bytes and len(img_bytes) > 2048:
                    web_bytes = compress_image_smart(img_bytes, max_dim=1200, quality=85)
                    gemini_bytes = compress_image_bytes(web_bytes, max_dim=768, quality=60)

                    if web_bytes and gemini_bytes:
                        downloaded_data.append({
                            "url": url,
                            "web_bytes": web_bytes,
                            "gemini_bytes": gemini_bytes
                        })
            except Exception:
                pass

    if not downloaded_data:
        add_log_event(state.message_id, "IMAGE_FINDER_DOWNLOAD_FAILED",
                      "دانلود بایت‌های تصاویر با شکست مواجه شد. انتقال به تولید تصویر.")
        return {"supervisor_decision": "generate"}

    api = ApiContainer.objects.filter(status=True, provider__in=["gemini", "google"]).order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.error("GEMINI_API_KEY not found.")
        add_log_event(state.message_id, "IMAGE_FINDER_ERROR", "کلید Gemini API یافت نشد. انتقال به تولید عکس.")
        return {"supervisor_decision": "generate"}

    prompt_text = (
        "You are the Lead Visual Editor at \"Teknovia\" (تکنوویا). You are presented with a series of candidate images downloaded from Google Images search results.\n"
        "Your objective is to evaluate these images against the original technical request and select the best, high-quality, authentic match.\n\n"
        f"### ORIGINAL VISUAL REQUIREMENT:\n\"{state.prompt}\"\n\n"
        "### STRICT EVALUATION PROTOCOL (BE REALISTIC & LENIENT):\n"
        "- We are a fast-paced technology news agency. We highly prefer using a real photo, a leaked render, or an authentic product shot, even if it represents a custom brand variation (e.g., an ASUS-branded graphics card instead of NVIDIA's reference design, or a conceptual model that represents the leak closely).\n"
        "- **When to APPROVE (has_match = true)**:\n"
        "  - Select the index (1-based) of the image that accurately represents the product, logo, or concept.\n"
        "  - The image must look professional, clean, and carrying high information density. \n"
        "  - Minor watermark text or small publisher logos are ACCEPTABLE because our editorial team can clean them up. Do not reject a perfectly valid photo just because of a small watermark.\n"
        "- **When to REJECT (has_match = false) & FALLBACK GENERATION**:\n"
        "  - Reject ONLY if the images are completely off-topic or represent a totally different product.\n"
        "  - If you reject (has_match = false), you MUST perform two crucial tasks:\n"
        "    1. Write a highly descriptive English text-to-image prompt in `fallback_prompt` to generate a gorgeous conceptual representation. Ensure you append: `\"no text, no letters, no typography, no words, clean visual representation\"`.\n"
        "    2. Write a brand-new, SEO-rich Persian alt text in `generated_alt_text` (under 100 characters). Since the final image will be an abstract/conceptual artwork rather than a real photo, you must write a Farsi alt text that describes this newly designed artistic scene (e.g., \"تصویر هنری انتزاعی از شبکه‌های عصبی و پردازش شناختی هوش مصنوعی\"). Do not use the original realistic alt text."
    )

    contents_payload = [
        {"type": "text", "text": prompt_text}
    ]

    for idx, item in enumerate(downloaded_data, 1):
        mime_type, _ = mimetypes.guess_type(item["url"])
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        img_b64 = base64.b64encode(item["gemini_bytes"]).decode("utf-8")

        contents_payload.append({
            "type": "text",
            "text": f"--- Candidate Image #{idx} ---"
        })
        contents_payload.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{img_b64}"
            }
        })

    selected_url = None
    selected_bytes = None
    fallback_prompt = None
    generated_alt_text = None
    go_to_generator = False

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            api_key=SecretStr(api_key),
            timeout=180
        ).with_structured_output(GeminiImageSelection)

        response = llm.invoke([
            SystemMessage(content="You are a meticulous visual content selector and prompt engineer."),
            HumanMessage(content=contents_payload)
        ])

        add_log_event(
            state.message_id,
            "GEMINI_OUTPUT_LOG",
            f"پاسخ جمینای دریافت شد. تطابق: {response.has_match} | اندیس: {response.selected_index or '-'}",
            {
                "has_match": response.has_match,
                "selected_index": response.selected_index,
                "reason_text": response.reason,
                "fallback_prompt": response.fallback_prompt,
                "generated_alt_text": response.generated_alt_text
            }
        )

        if response.has_match and response.selected_index:
            idx = response.selected_index - 1
            if 0 <= idx < len(downloaded_data):
                selected_url = downloaded_data[idx]["url"]
                selected_bytes = downloaded_data[idx]["web_bytes"]
                add_log_event(state.message_id, "IMAGE_FINDER_MATCHED",
                              f"تصویر شماره {response.selected_index} با شباهت عالی توسط جمینای انتخاب شد.")
            else:
                go_to_generator = True
                fallback_prompt = response.fallback_prompt or state.prompt
                generated_alt_text = response.generated_alt_text
        else:
            go_to_generator = True
            fallback_prompt = response.fallback_prompt or state.prompt
            generated_alt_text = response.generated_alt_text
            add_log_event(state.message_id, "IMAGE_FINDER_FALLBACK",
                          "تصویر مناسبی در وب یافت نشد. تولید پرامپت جایگزین برای عکس‌ساز.")

        if api:
            try:
                api.increment_usage()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error in Gemini Selection node: {e}", exc_info=True)
        add_log_event(state.message_id, "IMAGE_FINDER_ERROR",
                      f"خطا در مدل ارزیابی جمینای: {str(e)}. ارسال به تولیدکننده Z Image.")
        go_to_generator = True
        fallback_prompt = state.prompt

    if go_to_generator:
        return {
            "supervisor_decision": "generate",
            "fallback_prompt": fallback_prompt,
            "generated_alt_text": generated_alt_text
        }

    return {
        "selected_image_url": selected_url,
        "selected_image_bytes": selected_bytes
    }


def image_generator_node(state: ImageWorkflowState) -> Dict[str, Any]:
    """تولید تصویر هنری با به کارگیری مدل Z Image در سرویس deAPI به همراه سیستم فال‌بک پیشرفته و فوق‌العاده منعطف"""
    final_prompt = state.fallback_prompt or state.prompt
    logger.info("اجرای نود تولید تصویر از نو با استفاده از مدل Z Image...")
    add_log_event(state.message_id, "IMAGE_GENERATOR_START", "در حال تولید تصویر با کیفیت با مدل Z-Image-Turbo...")

    api = ApiContainer.objects.filter(status=True, provider__in=["deapi", "Deapi"]).order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("DEAPI_API_KEY")

    if not api_key:
        logger.error("DEAPI_API_KEY inside environment variables or DB is missing.")
        add_log_event(state.message_id, "IMAGE_GENERATOR_ERROR",
                      "کلید API مربوط به deAPI یافت نشد. استفاده از جایگزین باکیفیت پروداکشن...")
        return get_high_quality_production_fallback(state, final_prompt)

    url = "https://api.deapi.ai/api/v1/client/txt2img"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": final_prompt,
        "model": "ZImageTurbo_INT8",
        "width": 1024,
        "height": 768,
        "seed": -1,
        "steps": 20,
        "guidance": 3.5
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.status_code == 200:
            res_data = response.json()
            request_id = res_data.get("data", {}).get("request_id") or res_data.get("request_id")
            if not request_id:
                logger.error(f"Failed to retrieve request_id from deAPI response: {res_data}")
                return get_high_quality_production_fallback(state, final_prompt)

            add_log_event(state.message_id, "IMAGE_GENERATOR_SUBMITTED",
                          f"درخواست به deAPI ارسال شد. شناسه فرآیند: {request_id}. در حال پایش وضعیت...")

            status_url = f"https://api.deapi.ai/api/v2/jobs/{request_id}"
            delay = 2.0
            image_url = None
            for attempt in range(12):
                time.sleep(delay)
                try:
                    status_res = requests.get(status_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
                    if status_res.status_code == 200:
                        status_data = status_res.json()
                        job_data = status_data.get("data", {})
                        status = job_data.get("status") or job_data.get("state")
                        logger.info(f"deAPI Job {request_id} attempt {attempt + 1}: status={status}")
                        if status in ("completed", "done"):
                            image_url = job_data.get("result_url") or job_data.get("url") or job_data.get("image_url")
                            break
                        elif status == "failed":
                            logger.error(f"deAPI Job {request_id} marked as failed.")
                            break
                    else:
                        logger.warning(f"deAPI Polling status code: {status_res.status_code}")
                except Exception as poll_e:
                    logger.warning(f"Error during polling deAPI status: {poll_e}")

                delay = min(delay * 1.5, 8.0)

            if image_url:
                add_log_event(state.message_id, "IMAGE_GENERATOR_SUCCESS",
                              f"تصویر با مدل Z Image تولید شد: {image_url}")
                img_bytes = download_single_image_bytes(image_url, timeout=15)
                if img_bytes:
                    web_bytes = compress_image_smart(img_bytes, max_dim=1200, quality=85)

                    if api:
                        try:
                            api.increment_usage()
                        except Exception:
                            pass

                    return {
                        "selected_image_url": image_url,
                        "selected_image_bytes": web_bytes
                    }

            logger.error(f"Could not retrieve completed image from deAPI for job {request_id}")
            add_log_event(state.message_id, "IMAGE_GENERATOR_TIMEOUT",
                          "عدم پاسخ مناسب یا بروز تایم‌اوت در deAPI. استفاده از عکس پروداکشن جایگزین...")
        else:
            logger.error(f"deAPI txt2img call failed with status {response.status_code}: {response.text}")
            add_log_event(state.message_id, "IMAGE_GENERATOR_API_FAIL",
                          f"خطای وب سرویس deAPI: کد {response.status_code}")

    except Exception as e:
        logger.error(f"Error calling deAPI txt2img: {e}", exc_info=True)
        add_log_event(state.message_id, "IMAGE_GENERATOR_EXCEPTION", f"خطای استثنا در زمان ارتباط با deAPI: {str(e)}")

    return get_high_quality_production_fallback(state, final_prompt)


def image_saver_node(state: ImageWorkflowState) -> Dict[str, Any]:
    """ذخیره‌سازی تصویر و جایگزینی پویای تگ‌های مارک‌داون با Regex پایتون و پیوند اتمیک و تراکنش‌امنه به دیتابیس"""
    logger.info("اجرای نود نهایی و ذخیره‌ساز هوشمند تصاویر...")

    if not state.selected_image_bytes:
        logger.error("هیچ بایت تصویری برای ذخیره یافت نشد.")
        add_log_event(state.message_id, "IMAGE_SAVER_FAILED", "بایت‌های تصویر خالی بود؛ ذخیره‌سازی ناموفق.")
        return {}

    articles_updated = 0
    matching_articles = Content.objects.filter(suggestions__contains=[{"tracking_id": state.tracking_id}])

    # استخراج Alt Text اختصاصی و پویا از متن مارک‌داون مقاله به کمک Regex پایتون
    placeholder_pattern = rf"!\[(.*?)\]\(suggestion_id:{state.local_id}\)"

    extracted_alt_text = f"تصویر پیشنهادی شماره {state.local_id}"
    for article in matching_articles:
        match = re.search(placeholder_pattern, article.content)
        if match:
            extracted_alt_text = match.group(1)
            break

    # تعیین متن آلت نهایی: اگر عکس تولید شده است، از Alt Text پویایی که جمینای نوشته استفاده می‌کنیم
    if state.supervisor_decision == "find" and not state.fallback_prompt:
        final_alt_text = extracted_alt_text
    else:
        final_alt_text = state.generated_alt_text or f"طرح گرافیکی اختصاصی تک‌نیکا - {state.local_id}"

    # ۱. ثبت رسانه در MediaContainer به صورت تراکنشی ایمن
    try:
        with transaction.atomic():
            media_container = MediaContainer.objects.create(
                media_type=MediaContainer.MediaTypes.IMAGE,
                source_url=state.selected_image_url or "https://source.web",
                is_used=True,
                is_analyzed=True,
                alt_text=final_alt_text[:100],
                description=state.prompt
            )

            django_file = ContentFile(state.selected_image_bytes, name=f"ai_img_{state.tracking_id}.jpg")
            media_container.media.save(f"ai_img_{state.tracking_id}.jpg", django_file, save=True)

            logger.info(f"MediaContainer جدید ایجاد شد. ID={media_container.id}")
            add_log_event(state.message_id, "IMAGE_SAVER_SAVED_DB",
                          f"رسانه با شناسه جدید {media_container.id} در پایگاه‌داده با موفقیت ثبت شد.")
    except Exception as e:
        logger.error(f"Error saving image to MediaContainer: {e}", exc_info=True)
        add_log_event(state.message_id, "IMAGE_SAVER_DB_ERROR",
                      f"خطا در زمان درج فیزیکی فایل تصویر در دیتابیس: {str(e)}")
        return {}

    # ۲. پیوند تصویر به مقالات وب‌سایت مرتبط (Contents) و جایگزینی با Regex پایتون به صورت اتمیک
    try:
        with transaction.atomic():
            for article in matching_articles:
                # واکشی مجدد رکورد برای قفل موقت دیتابیس جهت ممانعت از تداخل همزمان
                article_locked = Content.objects.select_for_update().get(id=article.id)
                sugs = list(article_locked.suggestions or [])
                updated = False

                for s in sugs:
                    if s.get("tracking_id") == state.tracking_id:
                        s["status"] = "completed"
                        s["media_id"] = media_container.id
                        updated = True

                        placements = s.get("placements", [])
                        if "article_featured" in placements:
                            article_locked.featured_media = media_container
                            logger.info(f"تصویر شاخص مقاله {article_locked.id} تنظیم شد.")

                        if "article_inline" in placements:
                            replacement_tag = f"![{final_alt_text}](media_id:{media_container.id})"
                            article_locked.content = re.sub(placeholder_pattern, replacement_tag, article_locked.content)
                            logger.info(f"تگ تصویر پیشنهادی در مقاله {article_locked.id} با موفقیت به تگ رسانه استاندارد تبدیل شد.")

                if updated:
                    article_locked.suggestions = sugs
                    all_completed = all(s.get("status") == "completed" for s in sugs)
                    if all_completed:
                        article_locked.suggestions_status = Content.Suggestions.FINISHED
                        logger.info(f"تمام تصاویر پیشنهادی مقاله {article_locked.id} تکمیل شدند.")

                    article_locked.save()
                    articles_updated += 1
    except Exception as e:
        logger.error(f"Error linking image to matching contents: {e}", exc_info=True)

    # ۳. پیوند تصویر به پست‌های تلگرام مرتبط (PostsContainer) و ذخیره‌سازی اتمیک
    posts_to_trigger = []
    try:
        with transaction.atomic():
            matching_posts = PostsContainer.objects.filter(suggestions__contains=[{"tracking_id": state.tracking_id}])
            for post in matching_posts:
                post_locked = PostsContainer.objects.select_for_update().get(id=post.id)
                sugs = list(post_locked.suggestions or [])
                updated = False

                for s in sugs:
                    if s.get("tracking_id") == state.tracking_id:
                        s["status"] = "completed"
                        s["media_id"] = media_container.id
                        updated = True

                        placements = s.get("placements", [])
                        if "telegram_post" in placements:
                            post_locked.medias.add(media_container)
                            logger.info(f"رسانه {media_container.id} به پست تلگرام {post_locked.id} پیوست شد.")

                if updated:
                    post_locked.suggestions = sugs
                    all_completed = all(s.get("status") == "completed" for s in sugs)
                    if all_completed:
                        post_locked.suggestions_status = PostsContainer.Suggestions.FINISHED
                        logger.info(f"تمام تصاویر پیشنهادی پست تلگرام {post_locked.id} با موفقیت آماده شد.")
                        
                        if post_locked.state == PostsContainer.State.DRAFT:
                            posts_to_trigger.append(post_locked.id)

                    post_locked.save()
    except Exception as e:
        logger.error(f"Error linking image to matching posts: {e}", exc_info=True)

    # ۴. اجرای کاملاً ایمن تسک متمرکز انتشار در خارج از بلاک تراکنش (به محض Commit دیتابیس روی دیسک)
    if posts_to_trigger:
        for pid in posts_to_trigger:
            def trigger_publisher(post_id=pid):
                try:
                    from celery import current_app
                    current_app.send_task("workflows.tasks.process_publisher_workflow", args=[post_id])
                    add_log_event(state.message_id, "IMAGE_POST_TRIGGER_PUBLISHER",
                                  f"پست تلگرامی {post_id} جهت انتشار به تسک متمرکز فرستاده شد.")
                except Exception as celery_e:
                    logger.error(f"Error triggering publisher task: {celery_e}")

            # استفاده از قلاب بومی جنگو برای رهاسازی تسک پس از اتمام فیزیکی کوئری
            transaction.on_commit(trigger_publisher)

    add_log_event(
        state.message_id,
        "IMAGE_SAVER_COMPLETE",
        f"پایان موفق ورک‌فلو تصویر. اعمال روی {articles_updated} مقاله و {len(posts_to_trigger)} پست تلگرامی."
    )

    return {"media_id": media_container.id}


# ────────────────────────────────────────────────────────────────
# توابع شرطی ارکستراسیون لنگ‌چین (Conditional Routing Functions)
# ────────────────────────────────────────────────────────────────

def finder_routing(state: ImageWorkflowState) -> Literal["generator", "saver"]:
    if state.supervisor_decision == "generate":
        return "generator"
    return "saver"


# ────────────────────────────────────────────────────────────────
# ساخت، تعریف و کامپایل گراف تصاویر (Graph Compilation)
# ────────────────────────────────────────────────────────────────

def get_image_workflow_graph():
    """ساخت و کامپایل گراف پردازش موازی و شرطی تصاویر پیشنهادی"""
    workflow = StateGraph(ImageWorkflowState)

    workflow.add_node("supervisor", image_supervisor_node)
    workflow.add_node("finder", image_finder_node)
    workflow.add_node("generator", image_generator_node)
    workflow.add_node("saver", image_saver_node)

    workflow.add_edge(START, "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        supervisor_routing,
        {
            "finder": "finder",
            "generator": "generator"
        }
    )

    workflow.add_conditional_edges(
        "finder",
        finder_routing,
        {
            "generator": "generator",
            "saver": "saver"
        }
    )

    workflow.add_edge("generator", "saver")
    workflow.add_edge("saver", END)

    return workflow.compile()
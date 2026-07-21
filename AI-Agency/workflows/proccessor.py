import re
import base64
import mimetypes
import logging
import os
import io
import time
from typing import Optional

import requests
from PIL import Image

from django.core.files.base import ContentFile
from django.conf import settings

from langchain_core.tools import tool
from pydantic import BaseModel, Field, SecretStr
from langgraph.graph import START, END
from langgraph.types import Command
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI

from contents.models import MediaContainer
from accounts.models import ApiContainer
from workflows.models import ReceivedMessages
from workflows.vector_services import *
from workflows.logging_services import add_log_event, update_log_metadata

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# توابع کمکی فشرده‌سازی و دانلود محلی
# ────────────────────────────────────────────────────────────────

def download_single_image_bytes(url: str, timeout: int = 15) -> Optional[bytes]:
    """دانلود بایت‌های عکس با مدیریت هدر و تایم‌اوت"""
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


def compress_edited_image(img_bytes: bytes, max_dim: int = 1200, quality: int = 85) -> bytes:
    """
    فشرده‌سازی عکس ویرایش‌شده برای استقرار در وب با بهترین کیفیت و کارایی
    """
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
        logger.warning(f"Error compressing edited image: {e}")
        return img_bytes


# ────────────────────────────────────────────────────────────────
# استیت لنگ‌چین (LangGraph State)
# ────────────────────────────────────────────────────────────────

class MessageStates(BaseModel):
    raw_text: str
    message_id: int
    is_tech: bool
    is_exists: bool
    edit_requests: list[dict] = []


# ────────────────────────────────────────────────────────────────
# الگوهای ساختار یافته خروجی مدل (LLM Structured Schemas)
# ────────────────────────────────────────────────────────────────

class ObserverAnswer(BaseModel):
    is_relevant: bool = Field(
        description="True if the post is genuinely related to Technology/AI and is NOT an advertisement, sponsored content, or promotional material. False otherwise."
    )


class CheckerAnswer(BaseModel):
    is_exists: bool = Field(
        description="True if the incoming post is a duplicate or highly similar to any item in potential_duplicates. False if it is a unique news story."
    )


class MediaAnalysis(BaseModel):
    media_id: int = Field(
        description="The exact database ID of the media container being analyzed."
    )
    description: str = Field(
        description="A comprehensive, detailed description of what is depicted in this image/video. IMPORTANT: Ignore any source logos, watermark texts, or channel IDs that exist in the image — act as if they are not there so the writer doesn't reject the image."
    )
    alt_text: str = Field(
        description="A short, concise SEO-friendly alt text (under 100 characters) summarizing the media."
    )
    needs_edit: bool = Field(
        description="Set to True if the image contains watermarks, source logos, or channel names/IDs that should be removed to make it clean for publication. Otherwise False."
    )
    edit_instruction: Optional[str] = Field(
        None,
        description="If needs_edit is True, provide a precise instruction in English for removing the unwanted watermark/logo. Keep it simple and focused ONLY on erasing or removing elements (e.g. 'remove the circular logo at the top right', 'erase the watermark text in the bottom right corner'). Never request text translation or text modification."
    )


class AnalyzerAnswer(BaseModel):
    analyses: list[MediaAnalysis] = Field(
        description="List of analysis results for each provided media."
    )


# ────────────────────────────────────────────────────────────────
# پیاده‌سازی گام‌به‌گام نودها (Nodes Implementation)
# ────────────────────────────────────────────────────────────────

def observer_node(state: MessageStates):
    system = """
    You are an expert Telegram post observer. Your task is to analyze the content of a Telegram post and determine if it is genuinely related to Technology or Artificial Intelligence (AI), while filtering out any promotional content.

    ### CRITICAL RULE: FILTER OUT ADVERTISEMENTS
    You must classify any post as IRRELEVANT (is_relevant = False) if it contains advertisements, sponsored content, or promotional materials, even if it mentions technology or AI. Examples of content to reject:
    - VPN sales, proxy promotions, or premium account selling.
    - Technology courses, bootcamps, or webinars with promotional/sales intent.
    - Hosting services, domain sales, cloud server renting, or hardware promotions.
    - Channel advertisements, link exchanges, or non-tech job offers.

    ### Classification Guidelines:
    1. **Relevant (is_relevant = True):**
       - Genuine, informative, and high-quality posts about tech or AI.
       - News updates, software/hardware releases, coding tutorials, programming tips, scientific discussions, or open-source project introductions.
       - The primary intent of the post must be educational, informative, or news-oriented without any commercial/sales pitch.

    2. **Irrelevant (is_relevant = False):**
       - Any post categorized under the advertisement/promotional rule above.
       - Off-topic content (e.g., lifestyle, political news, general entertainment).
       - Low-quality, spam, or ambiguous text that does not clearly relate to tech or AI.
    """

    messages = [SystemMessage(content=system), HumanMessage(content=state.raw_text)]
    api = ApiContainer.objects.filter(status=True, provider="deepseek").order_by('today_use', '?').first()

    is_relevant = False
    if api:
        try:
            llm = ChatDeepSeek(
                api_key=SecretStr(api.key),
                model="deepseek-v4-pro",
                temperature=0.5,
                extra_body={"thinking": {"type": "disabled"}}
            ).with_structured_output(ObserverAnswer)

            response = llm.invoke(messages)
            is_relevant = response.is_relevant

            add_log_event(
                state.message_id,
                "OBSERVER",
                f"فیلتر هرزنامه و تحلیل محتوا انجام شد. مرتبط با تکنولوژی: {is_relevant}",
                {"is_relevant": is_relevant}
            )

            try:
                api.increment_usage()
            except AttributeError:
                api.today_use = (api.today_use or 0) + 1
                if hasattr(api, 'total_use'):
                    api.total_use = (api.total_use or 0) + 1
                api.save()
        except Exception as e:
            logger.error(f"Error in observer_node LLM: {e}")
            add_log_event(state.message_id, "OBSERVER_ERROR", f"خطا در ارتباط با مدل ناظر: {str(e)}")
            is_relevant = False

    # به‌روزرسانی فیلدهای مدل دیتابیس جنگو
    try:
        msg = ReceivedMessages.objects.get(id=state.message_id)
        msg.is_tech = is_relevant

        if is_relevant:
            msg.step = ReceivedMessages.Steps.CHECKING
        else:
            msg.step = ReceivedMessages.Steps.FINISHED
            msg.is_finished = True
        msg.save()
    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages with id {state.message_id} not found in observer_node")
    except Exception as e:
        logger.error(f"Error saving message fields in observer_node: {e}")

    if is_relevant:
        return Command(update={"is_tech": is_relevant}, goto="checker")
    else:
        return Command(update={"is_tech": is_relevant}, goto=END)


@tool
def check_duplicate(text: str) -> dict:
    """
    Checks if the given text is a duplicate of any existing items in both
    'contents' (published articles) and 'received_messages' (in-queue messages) collections.
    """
    embed = generate_text_embedding(text)

    contents_res = check_text_for_potential_duplicates(
        text, collection_name=settings.CONTENTS, embed=embed, high_threshold=0.92
    )

    received_res = check_text_for_potential_duplicates(
        text, collection_name=settings.RECEIVED, embed=embed, high_threshold=0.92
    )

    return {
        "contents": contents_res,
        "received": received_res
    }


def checker_node(state: MessageStates):
    check_results = check_duplicate.invoke({"text": state.raw_text})

    contents_res = check_results.get("contents", {})
    received_res = check_results.get("received", {})

    is_exists = False
    details_log = {}

    if contents_res.get("action") == "proceed" and received_res.get("action") == "proceed":
        is_exists = False
        add_log_event(state.message_id, "CHECKER_FAST_PASS",
                      "هیچ شباهت معنایی در سیستم برداری یافت نشد. خبر کاملاً یکتاست.")

    elif contents_res.get("action") == "duplicate_detected" or received_res.get("action") == "duplicate_detected":
        is_exists = True
        add_log_event(state.message_id, "CHECKER_FAST_PASS",
                      "تکراری بودن خبر با شباهت بالای ۹۲٪ در گام اول تایید شد. فرآیند متوقف می‌شود.")

    else:
        potential_duplicates = []
        if contents_res.get("action") == "agent_decision_required":
            potential_duplicates.extend(contents_res.get("potential_duplicates", []))
        if received_res.get("action") == "agent_decision_required":
            potential_duplicates.extend(received_res.get("potential_duplicates", []))

        system_prompt = """
        You are an expert AI content deduplication assistant. Your task is to compare an incoming Telegram post against a list of potential duplicate documents retrieved from our vector database.

        Analyze the incoming post and compare it with the content of EACH candidate in the list.

        ### Rules:
        - Set `is_exists` to True if the incoming post covers the exact same news story or contains the same update/information as any of the candidates (even if the wording, language, or structure is slightly different).
        - Set `is_exists` to False only if the incoming post is a completely different news story or covers a separate event.
        """

        formatted_candidates = ""
        for idx, candidate in enumerate(potential_duplicates, 1):
            formatted_candidates += f"""
            --- Candidate #{idx} ---
            Database ID: {candidate.get('django_id')}
            Type: {candidate.get('source_type')}
            Similarity Score: {candidate.get('similarity_score')}
            Content Text: {candidate.get('content_text')}
            -------------------------\n
            """

        user_content = f"""
        Incoming Post to Verify:
        {state.raw_text}\n

        Potential Duplicates Found in Database:
        {formatted_candidates}
        """

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]

        api = ApiContainer.objects.filter(status=True, provider="deepseek").order_by('today_use', '?').first()

        if api:
            try:
                llm = ChatDeepSeek(
                    api_key=SecretStr(api.key),
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    temperature=0.1,
                ).with_structured_output(CheckerAnswer)

                response = llm.invoke(messages)
                is_exists = response.is_exists
                details_log = response.model_dump()

                add_log_event(
                    state.message_id,
                    "CHECKER",
                    f"تصمیم بررسی معنایی تکراری بودن اتخاذ شد. آیا تکراری است: {is_exists}",
                    details_log
                )

                try:
                    api.increment_usage()
                except AttributeError:
                    api.today_use = (api.today_use or 0) + 1
                    if hasattr(api, 'total_use'):
                        api.total_use = (api.total_use or 0) + 1
                    api.save()
            except Exception as e:
                logger.error(f"Error invoking DeepSeek in checker_node: {e}")
                add_log_event(state.message_id, "CHECKER_ERROR", f"خطا در فراخوانی مدل ارزیابی تکراری بودن: {str(e)}")
                is_exists = any(item.get("similarity_score", 0) > 0.85 for item in potential_duplicates)
        else:
            is_exists = any(item.get("similarity_score", 0) > 0.85 for item in potential_duplicates)

    try:
        msg = ReceivedMessages.objects.get(id=state.message_id)
        msg.is_exists = is_exists

        if is_exists:
            msg.step = ReceivedMessages.Steps.FINISHED
            msg.is_finished = True
        else:
            msg.step = ReceivedMessages.Steps.FETCHING

        msg.save()
    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages with id {state.message_id} not found in checker_node")
    except Exception as e:
        logger.error(f"Error saving message fields in checker_node: {e}")

    if is_exists:
        return Command(update={"is_exists": is_exists}, goto=END)
    else:
        return Command(update={"is_exists": is_exists}, goto="fetcher")


def extract_links(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r'(https?://[^\s]+)', text)


def fetcher_node(state: MessageStates):
    links = extract_links(state.raw_text)

    if not links:
        try:
            msg = ReceivedMessages.objects.get(id=state.message_id)
            msg.step = ReceivedMessages.Steps.ANALYZING
            msg.save()
        except ReceivedMessages.DoesNotExist:
            logger.error(f"ReceivedMessages with id {state.message_id} not found in fetcher_node")

        add_log_event(state.message_id, "FETCHER", "هیچ لینکی در متن خبر ورودی یافت نشد؛ انتقال به گام بعد.")
        return Command(goto="analyzer")

    api = ApiContainer.objects.filter(status=True, provider__in=["gemini", "google"]).order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("GEMINI_API_KEY")

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        api_key=SecretStr(api_key) if api_key else None,
        thinking_level="high",
    ).bind_tools([{"url_context": {}}])

    system_instruction = """
    You are the Senior Intelligence Agent in charge of deep web extraction and synthesis. 
    Your primary tool is Google's native `url_context` tool, which allows you to ingest and reason over the full content of multiple public web pages simultaneously.

    ### EXECUTIVE TASK:
    You are provided with a list of raw URLs. Your job is to trigger your native `url_context` tool once to load and summarize ALL these URLs in parallel.

    ### STRICT OPERATIONAL MANDATES:

    1. **BATCH INGESTION**:
       - Ingest all the provided URLs in a single parallel operation. Do not request them one by one.

    2. **STRICT ANTI-HALLUCINATION GUARDRAIL (NO SLUG-GUESSING)**:
       - If a URL cannot be accessed due to Cloudflare protection, 403 Forbidden, 404 Not Found, or any other restriction, you must NOT speculate, make assumptions, or guess the contents based on the URL path or keywords.
       - If a URL fails to load, explicitly flag it in the output exactly as follows:
         `[EXTRACTION_STATUS: FAILED] - URL: <insert_url> - Reason: <specific_error_or_unreachable>`
       - This failure tag is highly critical as it signals our down-stream Supervisor to initiate a compensatory Tavily web search.

    3. **CLEAN MARKDOWN SYNTHESIS (ZERO METADATA & TELEMETRY)**:
       - You must NOT output raw JSON dumps, nested dictionary structures (e.g., `[{'type': 'text', ...}]`), signature hashes, or internal telemetry logs.
       - Provide the final output as a clean, highly-dense, and beautifully formatted Persian Markdown summary. 
       - Structure each successfully extracted URL's content under its clear Persian heading, capturing all key technical specifications, statistics, and chronological details to ensure the Writer Agent has the highest quality factual data.
    """

    user_content = "Please extract the contents of the following links and summarize them:\n" + "\n".join(links)
    messages = [
        SystemMessage(content=system_instruction),
        HumanMessage(content=user_content)
    ]

    extracted_content = ""
    try:
        response = llm.invoke(messages)
        extracted_content = response.content

        add_log_event(state.message_id, "FETCHER",
                      f"محتوای تعداد {len(links)} وب‌سایت با استفاده از جمینای استخراج و خلاصه‌سازی شد.")

        if api:
            try:
                api.increment_usage()
            except AttributeError:
                api.today_use = (api.today_use or 0) + 1
                if hasattr(api, 'total_use'):
                    api.total_use = (api.total_use or 0) + 1
                api.save()

    except Exception as e:
        logger.error(f"Error fetching URL contents in fetcher_node: {e}")
        add_log_event(state.message_id, "FETCHER_ERROR", f"خطا در فرآیند استخراج محتویات وب‌سایت‌ها: {str(e)}")
        failed_reports = []
        for url in links:
            failed_reports.append(f"[EXTRACTION_STATUS: FAILED] - URL: {url} - Reason: Network Exception during fetch.")
        extracted_content = "\n".join(failed_reports)

    clean_extracted_text = str(extracted_content).strip()
    if clean_extracted_text.startswith("[{") and clean_extracted_text.endswith("}]"):
        try:
            clean_extracted_text = re.sub(r"'extras':\s*\{.*?\}", "", clean_extracted_text)
            clean_extracted_text = re.sub(r"'signature':\s*'.*?'", "", clean_extracted_text)
            clean_extracted_text = clean_extracted_text.replace("{'type': 'text', 'text': '", "").replace("'}", "")
        except Exception as clean_err:
            logger.warning(f"Error while extra sanitization of fetcher output: {clean_err}")

    try:
        msg = ReceivedMessages.objects.get(id=state.message_id)
        msg.links = f"URLs Found:\n" + "\n".join(links) + f"\n\n=== Extracted Web Contents ===\n{clean_extracted_text}"
        msg.step = ReceivedMessages.Steps.ANALYZING
        msg.save()
    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages with id {state.message_id} not found in fetcher_node")
    except Exception as e:
        logger.error(f"Error saving message fields in fetcher_node: {e}")

    return Command(goto="analyzer")


def analyzer_node(state: MessageStates):
    try:
        msg = ReceivedMessages.objects.get(id=state.message_id)
        media_list = msg.medias.all()
    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages with id {state.message_id} not found in analyzer_node")
        return Command(goto="saver")

    if not media_list.exists():
        try:
            msg.step = ReceivedMessages.Steps.SAVING
            msg.save()
        except Exception as e:
            logger.error(f"Error updating step in analyzer_node (no media): {e}")
        add_log_event(state.message_id, "ANALYZER", "هیچ رسانه‌ای همراه با خبر برای آنالیز مالتی‌مدیا یافت نشد.")
        return Command(goto="saver")

    api = ApiContainer.objects.filter(status=True, provider__in=["gemini", "google"]).order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("GEMINI_API_KEY")

    context_instruction = (
        "You are the Senior Multimodal Art Director and Visual Quality Inspector.\n"
        "You are given a raw technology news text as context, alongside one or more media files (images/videos) associated with it.\n"
        "Your objective is to perform a high-fidelity visual analysis of each media item and determine if it requires professional cleanup (watermark/logo removal) before publication.\n\n"
        f"### RAW NEWS CONTEXT:\n{state.raw_text}\n\n"
        "### DETAILED WATERMARK & CLEANUP RULES:\n"
        "1. **Needs Edit (needs_edit = true)**:\n"
        "   - If the image contains publisher/source watermarks, overlay text, source website URLs (e.g., \"digiato.com\", \"zoomit.ir\"), or Telegram channel handles (e.g., \"@geetnews\", \"t.me/...\") stamped on top of the picture.\n"
        "   - These elements must be removed to make our final article look clean and exclusive.\n"
        "2. **Does NOT Need Edit (needs_edit = false)**:\n"
        "   - Genuine product branding, model names, official device logos, or text that is physically part of the hardware/software interface described in the news context (e.g., the \"Windows\" logo on a laptop screen, \"RTX\" text on a graphics card).\n"
        "3. **CRITICAL WARNING: NO SCREENSHOT OR WEBSITE UI TAMPERING (PRESERVE ALL UI ELEMENTS)**:\n"
        "   - If the media item is a screenshot of a website, online store, product list, app interface, or software dashboard, you must NEVER treat native UI elements as watermarks.\n"
        "   - Do NOT try to remove website features, product listing tags, 'NEW' or 'SALE' ribbons, 'Add to compare' checkboxes, prices, cart buttons, menus, or rating stars. These are integral parts of the screenshot and MUST be preserved.\n"
        "   - Only flag `needs_edit = true` if a separate, third-party competitor watermark (like a Telegram channel ID) is explicitly stamped on top of the screenshot.\n"
        "4. **Edit Instruction Guidelines**:\n"
        "   - If `needs_edit` is true, write a highly concise, surgical instruction in English for the image editor model (e.g., \"remove the watermark text in the bottom right corner\", \"erase the circular channel logo in the top left\"). Focus ONLY on erasing; do not request text translation or UI manipulation.\n\n"
        "### DESCRIPTION & ALT TEXT:\n"
        "- In `description`, describe the image in rich detail for the writer's reference. Ignore the watermarks during description—describe only the actual tech subject as if it is already clean.\n"
        "- In `alt_text`, provide a highly concise, SEO-friendly Farsi description (under 100 characters) for the web."
    )

    contents = [
        {
            "type": "text",
            "text": context_instruction
        }
    ]

    processed_media_count = 0

    for media_container in media_list:
        if not media_container.media:
            continue

        if media_container.media_type == MediaContainer.MediaTypes.IMAGE:
            try:
                media_container.media.open('rb')
                img_bytes = media_container.media.read()
                media_container.media.close()
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')

                mime_type, _ = mimetypes.guess_type(media_container.media.name)
                if not mime_type:
                    mime_type = "image/jpeg"

                contents.append({
                    "type": "text",
                    "text": f"Below is the image with Database ID: {media_container.id}"
                })
                contents.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{img_base64}"
                    }
                })
                processed_media_count += 1
            except Exception as e:
                logger.error(f"Error encoding image ID {media_container.id}: {e}")

        elif media_container.media_type == MediaContainer.MediaTypes.VIDEO:
            try:
                media_container.media.open('rb')
                video_bytes = media_container.media.read()
                media_container.media.close()
                video_base64 = base64.b64encode(video_bytes).decode('utf-8')

                mime_type, _ = mimetypes.guess_type(media_container.media.name)
                if not mime_type:
                    mime_type = "video/mp4"

                contents.append({
                    "type": "text",
                    "text": f"Below is the video with Database ID: {media_container.id}"
                })
                contents.append({
                    "type": "media",
                    "mime_type": mime_type,
                    "data": video_base64
                })
                processed_media_count += 1
            except Exception as e:
                logger.error(f"Error encoding video ID {media_container.id}: {e}")

    if processed_media_count == 0:
        try:
            msg.step = ReceivedMessages.Steps.SAVING
            msg.save()
        except Exception as e:
            logger.error(f"Error updating step to SAVING in analyzer_node: {e}")
        return Command(goto="saver")

    messages = [
        SystemMessage(
            content="You are a meticulous SEO, media and context analyzer. You can analyze video and images in-depth. For any source logo or watermark present in the images, act as if they do not exist and analyze only the primary scene."),
        HumanMessage(content=contents)
    ]

    edit_requests = []

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            api_key=SecretStr(api_key) if api_key else None,
            thinking_level="high",
            timeout=180,
        ).with_structured_output(AnalyzerAnswer)

        response = llm.invoke(messages)

        add_log_event(state.message_id, "ANALYZER",
                      f"تحلیل مالتی‌مدیا تمام شد. تعداد {processed_media_count} رسانه پردازش شدند.")

        for analysis in response.analyses:
            try:
                media_item = msg.medias.get(id=analysis.media_id)
                media_item.description = analysis.description
                media_item.alt_text = analysis.alt_text[:100]
                media_item.is_analyzed = True
                media_item.save()

                if analysis.needs_edit and analysis.edit_instruction and media_item.media_type == MediaContainer.MediaTypes.IMAGE:
                    edit_requests.append({
                        "media_id": analysis.media_id,
                        "instruction": analysis.edit_instruction
                    })
                    logger.info(
                        f"Media ID {media_item.id} candidacy for Qwen Image Edit with instruction: {analysis.edit_instruction}")

            except MediaContainer.DoesNotExist:
                logger.warning(f"MediaContainer with ID {analysis.media_id} from Gemini response not found in message.")
            except Exception as inner_e:
                logger.error(f"Error saving analysis for MediaContainer ID {analysis.media_id}: {inner_e}")

        if api:
            try:
                api.increment_usage()
            except AttributeError:
                api.today_use = (api.today_use or 0) + 1
                if hasattr(api, 'total_use'):
                    api.total_use = (api.total_use or 0) + 1
                api.save()

    except Exception as e:
        logger.error(f"Error running multimodal video/image analysis in analyzer_node: {e}")
        add_log_event(state.message_id, "ANALYZER_ERROR", f"خطا در تحلیل رسانه‌ها توسط مدل: {str(e)}")

    try:
        msg.step = ReceivedMessages.Steps.SAVING
        msg.save()
    except Exception as e:
        logger.error(f"Error updating message step to SAVING: {e}")

    if edit_requests:
        add_log_event(state.message_id, "ANALYZER_EDIT_TRIGGERED",
                      f"تعداد {len(edit_requests)} تصویر شناسایی شد که نیاز به ادیت دارند. انتقال به نود ادیتور...")
        return Command(update={"edit_requests": edit_requests}, goto="image_editor")

    return Command(goto="saver")


def image_editor_node(state: MessageStates):
    """
    نود ویرایش هوشمند تصاویر: ارسال تصویر به مدل Qwen Image Edit Plus جهت پاک‌سازی لوگو و واتر مارک
    """
    logger.info("اجرای نود ادیتور هوشمند تصاویر...")
    add_log_event(state.message_id, "IMAGE_EDITOR_START",
                  f"در حال آغاز ویرایش تعداد {len(state.edit_requests)} تصویر کاندید...")

    api = ApiContainer.objects.filter(status=True, provider__in=["deapi", "Deapi"]).order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("DEAPI_API_KEY")

    if not api_key:
        logger.error("DEAPI_API_KEY is missing for image editor node.")
        add_log_event(state.message_id, "IMAGE_EDITOR_ERROR", "کلید deAPI یافت نشد؛ ویرایش تصاویر نادیده گرفته شد.")
        return Command(goto="saver")

    edited_count = 0

    for req in state.edit_requests:
        media_id = req["media_id"]
        instruction = req["instruction"]

        try:
            media_item = MediaContainer.objects.get(id=media_id)
            if media_item.media_type != MediaContainer.MediaTypes.IMAGE or not media_item.media:
                continue

            media_item.media.open('rb')
            img_bytes = media_item.media.read()
            media_item.media.close()

            logger.info(f"ارسال تصویر {media_id} به Qwen Image Edit برای حذف واترمارک: {instruction}")
            add_log_event(state.message_id, "IMAGE_EDITOR_SUBMIT", f"ارسال تصویر {media_id} با دستور: {instruction}")

            url = "https://api.deapi.ai/api/v2/images/edits"
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            files = {
                "image": ("image.jpg", img_bytes, "image/jpeg")
            }
            data = {
                "model": "QwenImageEdit_Plus_NF4",
                "prompt": instruction,
                "steps": 15,
                "seed": -1
            }

            response = requests.post(url, headers=headers, data=data, files=files, timeout=35)
            if response.status_code == 200:
                res_data = response.json()
                request_id = res_data.get("data", {}).get("request_id") or res_data.get("request_id")

                if not request_id:
                    logger.error(f"Failed to get request_id for media edit: {res_data}")
                    continue

                status_url = f"https://api.deapi.ai/api/v2/jobs/{request_id}"
                delay = 3.0
                image_url = None

                for attempt in range(30):
                    time.sleep(delay)
                    try:
                        status_res = requests.get(status_url, headers={"Authorization": f"Bearer {api_key}"},
                                                  timeout=10)
                        if status_res.status_code == 200:
                            status_data = status_res.json()
                            job_data = status_data.get("data", {})
                            status = job_data.get("status") or job_data.get("state")
                            logger.info(f"deAPI Job {request_id} attempt {attempt + 1}: status={status}")

                            if status in ("completed", "done"):
                                image_url = job_data.get("result_url") or job_data.get("url") or job_data.get(
                                    "image_url")
                                break
                            elif status == "failed":
                                logger.error(f"deAPI Edit Job {request_id} marked as failed.")
                                break
                        else:
                            logger.warning(f"deAPI Polling status code: {status_res.status_code}")
                    except Exception as poll_e:
                        logger.warning(f"Error polling deAPI edit status: {poll_e}")

                    delay = min(delay * 1.5, 10.0)

                if image_url:
                    edited_bytes = download_single_image_bytes(image_url, timeout=15)
                    if edited_bytes:
                        optimized_bytes = compress_edited_image(edited_bytes, max_dim=1200, quality=85)

                        original_filename = os.path.basename(media_item.media.name)
                        django_file = ContentFile(optimized_bytes, name=original_filename)

                        media_item.media.save(original_filename, django_file, save=True)
                        logger.info(f"تصویر {media_id} با موفقیت ویرایش و روی فایل قبلی بازنویسی شد.")
                        add_log_event(state.message_id, "IMAGE_EDITOR_SUCCESS",
                                      f"تصویر {media_id} با موفقیت ادیت و جایگزین شد.")
                        edited_count += 1
                else:
                    logger.error(f"Job {request_id} did not yield a result_url within timeout.")
            else:
                logger.error(f"deAPI image edit API call failed: {response.status_code} - {response.text}")

        except MediaContainer.DoesNotExist:
            logger.warning(f"MediaContainer {media_id} not found during editing.")
        except Exception as ex:
            logger.error(f"Error editing image {media_id}: {ex}", exc_info=True)

    if api and edited_count > 0:
        try:
            api.increment_usage(amount=edited_count)
        except Exception:
            pass

    add_log_event(state.message_id, "IMAGE_EDITOR_COMPLETE",
                  f"پان موفقیت‌آمیز عملیات ادیت تصاویر. تعداد {edited_count} تصویر پاک‌سازی شدند.")
    return Command(goto="saver")


def saver_node(state: MessageStates):
    try:
        msg = ReceivedMessages.objects.get(id=state.message_id)
    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages with id {state.message_id} not found in saver_node")
        return Command(goto=END)

    vector = generate_text_embedding(msg.raw_text)

    if vector:
        try:
            msg.set_embedding(vector)

            external_id = add_document_to_vector_index(
                collection_name=settings.RECEIVED,
                django_id=msg.id,
                vector=vector
            )

            if external_id is not None:
                msg.external_id = external_id
                logger.info(f"Successfully indexed message {msg.id} in TurboVec with external_id {external_id}")
                add_log_event(
                    state.message_id,
                    "INDEXER",
                    f"امبدینگ متن خبر تولید و با شناسه {external_id} در TurboVec ثبت شد."
                )
            else:
                logger.warning(f"Vector sync completed but external_id was not returned for message {msg.id}")
                add_log_event(state.message_id, "INDEXER_WARNING",
                              "پردازش بردار خبر انجام شد اما شناسه خارجی دریافت نشد.")

        except Exception as e:
            logger.error(f"Error handling vector storage operations for message {msg.id}: {e}")
            add_log_event(state.message_id, "INDEXER_ERROR", f"خطا در درج در پایگاه داده برداری: {str(e)}")
    else:
        logger.error(f"Could not generate embedding for message {msg.id}")
        add_log_event(state.message_id, "INDEXER_ERROR", "امکان تولید بردار متنی فراهم نشد.")

    try:
        msg.step = ReceivedMessages.Steps.FINISHED
        msg.is_finished = True
        msg.save()
    except Exception as e:
        logger.error(f"Error finalizing steps for message {msg.id} in saver_node: {e}")

    return Command(goto=END)
import os
import re
import io
import uuid
import logging
import time
import datetime
from typing import List, Dict, Any, Optional, Literal, Annotated
from pydantic import BaseModel, Field, SecretStr

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI

from django.conf import settings
from accounts.models import ApiContainer
from workflows.models import ReceivedMessages, WorkflowLog
from contents.models import Content, MediaContainer, PostsContainer
from workflows.writer_schema import WriterOutputSchema, GlobalSuggestion
from workflows.logging_services import add_log_event, update_log_metadata, finalize_log

logger = logging.getLogger(__name__)

# ایمپورت ایمن کتابخانه تقویم شمسی جهت تاریخ نگاری پویا
try:
    import jdatetime
except ImportError:
    jdatetime = None


# ────────────────────────────────────────────────────────────────
# متدهای کمکی تاریخ‌نگاری پویا و بومی برای سال ۲۰۲۶
# ────────────────────────────────────────────────────────────────

def get_current_dates() -> tuple[str, str]:
    """
    محاسبه و دریافت داینامیک تاریخ‌های جاری میلادی و شمسی سیستم
    بدون نیاز به هاردکد کردن مقادیر زمانی.
    """
    now = datetime.datetime.now()
    # فرمت میلادی: "Monday, July 19, 2026"
    gregorian_str = now.strftime("%A, %B %d, %Y")

    # فرمت شمسی ایمن به همراه استخراج نام ماه‌ها و روزهای هفته به فارسی
    shamsi_str = ""
    if jdatetime:
        try:
            j_now = jdatetime.datetime.now()
            weekdays = {
                0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنج‌شنبه",
                4: "جمعه", 5: "شنبه", 6: "یک‌شنبه"
            }
            wd = now.weekday()
            wd_name = weekdays.get(wd, "روز نامشخص")

            months = {
                1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
                5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
                9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"
            }
            m_name = months.get(j_now.month, "ماه نامشخص")
            shamsi_str = f"{wd_name}، {j_now.day} {m_name} {j_now.year}"
        except Exception as e:
            logger.warning(f"Error formatting jdatetime: {e}")
            shamsi_str = "یک‌شنبه، ۲۹ تیر ۱۴۰۵"
    else:
        # مکانیزم لایه دفاعی عددی در صورت عدم وجود پکیج شمسی
        shamsi_str = "یک‌شنبه، ۲۹ تیر ۱۴۰۵"

    return gregorian_str, shamsi_str


# ────────────────────────────────────────────────────────────────
# توابع کمکی ماژولار تصاویر مارک‌داون
# ────────────────────────────────────────────────────────────────

def get_media_placeholder(media_id: int, alt_text: str = "تصویر") -> str:
    """تولید تگ نگهدارنده مارک‌داون برای رسانه موجود"""
    clean_alt = alt_text.strip() if alt_text else "تصویر"
    return f"![{clean_alt}](media_id:{media_id})"


def parse_media_placeholders(markdown_content: str) -> List[int]:
    """استخراج تمامی شناسه‌های رسانه به کار رفته در متن از ساختار ![alt](media_id:ID)"""
    if not markdown_content:
        return []
    pattern = r"!\[.*?\]\(media_id:(\d+)\)"
    matches = re.findall(pattern, markdown_content)
    return [int(m) for m in matches]


def replace_media_placeholders(markdown_content: str, media_urls: Dict[int, str]) -> str:
    """جایگزینی آدرس‌های واقعی با ساختار جایگزین ![alt](media_id:ID)"""
    if not markdown_content:
        return ""
    pattern = r"!\[(.*?)\]\(media_id:(\d+)\)"

    def replacer(match):
        alt_text = match.group(1)
        media_id = int(match.group(2))
        actual_url = media_urls.get(media_id)
        if actual_url:
            return f"![{alt_text}]({actual_url})"
        return match.group(0)

    return re.sub(pattern, replacer, markdown_content)


# ────────────────────────────────────────────────────────────────
# تعریف ابزار یکتای عامل تحقیق (Tavily Single-Query Tool)
# ────────────────────────────────────────────────────────────────

@tool
def search_web_for_news(query: str) -> str:
    """
    Searches the web for a single, focused keyword-based query using Tavily.
    Always pass a single, clean string query. Do not pass multiple queries or arrays.
    """
    if not isinstance(query, str):
        query = str(query)
    query = query.strip()

    tavily = TavilySearch(max_results=3)
    last_error = ""
    for attempt in range(1, 4):
        try:
            res = tavily.invoke({"query": query})
            return f"=== Search Results for: '{query}' ===\n{str(res)}"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Attempt {attempt} failed searching for query '{query}': {e}")
            time.sleep(1)

    return f"=== Error searching '{query}': Failed after 3 attempts. Error: {last_error} ==="


# ────────────────────────────────────────────────────────────────
# تعریف وضعیت گراف (State Schema with Pydantic)
# ────────────────────────────────────────────────────────────────

class WriterWorkflowState(BaseModel):
    received_message_id: int = Field(default=0)
    raw_text: str = Field(default="")
    links_content: str = Field(default="")
    medias_info: List[Dict[str, Any]] = Field(default_factory=list)

    research_queries: List[str] = Field(default_factory=list)
    research_results: str = Field(default="")
    supervisor_decision: str = Field(default="")
    supervisor_task: str = Field(default="")

    messages: Annotated[list, add_messages] = Field(default_factory=list)
    writer_output: Optional[WriterOutputSchema] = Field(default=None)


class SupervisorDecision(BaseModel):
    decision: Literal["write", "research", "skip"] = Field(
        ...,
        description="مسیر سردبیری: 'write' اطلاعات کافی است، 'research' نیاز به جستجو دارد، 'skip' پیام هرزنامه یا تبلیغاتی است."
    )
    task: str = Field(..., description="تسک، ابهامات یا دستورالعمل دقیقی که عامل مربوطه باید انجام دهد.")


# ────────────────────────────────────────────────────────────────
# پیاده‌سازی گام‌به‌گام نودها (Nodes Implementation)
# ────────────────────────────────────────────────────────────────

def supervisor_node(state: WriterWorkflowState) -> Dict[str, Any]:
    logger.info("اجرای نود سوپروایزر سردبیری...")

    medias_summary = ""
    for idx, m in enumerate(state.medias_info, 1):
        medias_summary += f"رسانه #{idx} [شناسه={m['id']}]: نوع={m['type']} | توضیحات={m['description']} | تگ جایگزین={m['alt_text']}\n"

    # چک کردن سیستمی شکست در بارگذاری لینک‌ها جهت تغییر مسیر خودکار به سرچ
    extraction_failed = "[EXTRACTION_STATUS: FAILED]" in state.links_content
    additional_instruction = ""
    if extraction_failed:
        additional_instruction = (
            "\n\n🚨 CRITICAL NOTICE: One or more reference links in the previous extraction step failed to load. "
            "You MUST set your decision to 'research' and issue a clear instruction to search and recover the lost details of those failed links."
        )

    system_prompt = f"""
    You are the Chief Editorial Director and Technical Coordinator.
    Your critical task is to triage the incoming raw tech news alongside any retrieved web contents to determine the absolute best editorial pipeline.

    You must output a highly structured decision with the following options:
    1. **write**: Select this if the available raw text and retrieved links contain fully complete, factually rich, and technically detailed information. The facts must be sufficient to draft a premium website article and a Telegram post without requiring further verification.
    2. **research**: Select this if there are technical blindspots, vague statements, missing specifications, or if the previous link extraction step reported a `[FAILED]` status. You must provide clear, explicit instructions on exactly what factual gaps the Researcher must search for on the web.
    3. **skip**: Select this only if the raw content is spam, completely promotional, or lacks any informational value for a prestigious tech agency.
    {additional_instruction}
    """

    user_content = f"""
    متن خام خبر:
    {state.raw_text}

    محتوای وب استخراج شده:
    {state.links_content}

    رسانه‌های همراه:
    {medias_summary}
    """

    api = ApiContainer.objects.filter(status=True, provider="deepseek").order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("DEEPSEEK_API_KEY")

    decision = "write"
    task = "فراخوانی مدل با خطا مواجه شد؛ انتقال مستقیم به مرحله نویسندگی به عنوان روش محافظه‌کارانه."

    if api_key:
        try:
            llm = ChatDeepSeek(
                api_key=SecretStr(api_key),
                model="deepseek-v4-flash",
                temperature=0.1,
                extra_body={"thinking": {"type": "disabled"}}
            ).with_structured_output(SupervisorDecision)

            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            decision = response.decision
            task = response.task

            # مهار خودکار وضعیت برای اجبار به تحقیق در زمان بروز خطا در بارگذاری لینک‌ها
            if extraction_failed:
                decision = "research"
                task = "یکی یا چند مورد از لینک‌های مرجع در مرحله قبلی لود نشدند. حتماً اطلاعات تکمیلی و مشخصات فنی دقیق مربوط به خبر را با ابزار سرچ Tavily واکشی و راستی‌آزمایی کنید."

            add_log_event(
                state.received_message_id,
                "WRITER_SUPERVISOR",
                f"تصمیم سردبیری اتخاذ شد: {decision} | تسک ارجاعی: {task}",
                {"task": task, "decision": decision}
            )

            if api:
                api.increment_usage()
        except Exception as e:
            logger.error(f"Error in Supervisor DeepSeek node: {e}", exc_info=True)
            add_log_event(state.received_message_id, "WRITER_SUPERVISOR_ERROR", f"خطا در مدل تصمیم‌گیری ناظر: {str(e)}")

    return {"supervisor_decision": decision, "supervisor_task": task}


def supervisor_routing(state: WriterWorkflowState) -> Literal["researcher", "saver", "writer"]:
    dec = state.supervisor_decision
    if dec == "research":
        return "researcher"
    elif dec == "skip":
        return "saver"
    else:
        return "writer"


def researcher_node(state: WriterWorkflowState) -> Dict[str, Any]:
    logger.info("اجرای نود تحقیقگر به صورت زنجیره‌ای و گام‌به‌گام...")

    # محاسبه بودجه به کار رفته بر اساس تعداد پیام‌های ابزار (ToolMessages) در استیت گراف
    tool_calls_made = 0
    for msg in state.messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls_made += len(msg.tool_calls)

    remaining_budget = max(0, 3 - tool_calls_made)
    logger.info(f"Researcher current progress: {tool_calls_made} tool calls made. Remaining budget: {remaining_budget}")

    api = ApiContainer.objects.filter(status=True, provider="deepseek").order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("DEEPSEEK_API_KEY")

    llm = ChatDeepSeek(
        api_key=SecretStr(api_key) if api_key else None,
        model="deepseek-v4-flash",
        temperature=0.2,
        extra_body={"thinking": {"type": "disabled"}}
    ).bind_tools([search_web_for_news])

    task_injection = ""
    if state.supervisor_task:
        task_injection = f"\n\n**Editorial Directive (Task to complete):**\n{state.supervisor_task}\n"

    # استخراج پویا و سیستمی تاریخ جاری
    greg_date, jalali_date = get_current_dates()

    system_instruction = (
        "You are the Senior Investigative Research Journalist. Your mission is to perform sequential, deep, adaptive web searches to fill in technical blindspots, verify news integrity, and retrieve precise technical specifications.\n\n"
        f"### CURRENT CALENDAR SIGNAL:\n- Gregorian Date: {greg_date}\n- Persian Jalali Date: {jalali_date}\nKeep this temporal anchor in mind to evaluate chronological context and sequence events.\n\n"
        "### STRICT SEQUENTIAL SEARCH RULES:\n"
        "1. **ONE QUERY AT A TIME (CRITICAL)**: You must strictly output ONLY ONE tool call (`search_web_for_news`) in a single turn. Do not generate multiple parallel tool calls or lists of queries.\n"
        "2. **ADAPTIVE STEP-BY-STEP THINKING**:\n"
        "   - Run your first search query broadly to identify key entities, names, or general facts (e.g. 'nvidia newest AI chip').\n"
        "   - Inspect the results carefully. From those results, extract specific names, codenames, or model codes (e.g. you discover it is called 'Blackwell Ultra' or 'B300').\n"
        "   - Use your next search query to drill deeper into that newly-discovered specific entity (e.g. 'Nvidia B300 Blackwell Ultra specs launch date').\n"
        "   - Never run overlapping, redundant, or similar queries. Build each query on top of the knowledge gained from previous search results.\n"
        "3. **NO HARDCODED YEARS**: Never append calendar years (e.g. '2025', '2026') to your queries unless strictly necessary for historical context. Let search engines naturally rank fresh content.\n"
        f"4. **STRICT BUDGET LIMIT**: You have an absolute maximum of 3 search queries total across this entire session.\n"
        f"   - **Your Remaining Search Budget for this turn: {remaining_budget} queries.**\n"
        "   - If your remaining budget is 0, you MUST NOT call any tools. Summarize your current findings and write the final technical research report."
        "   - If your remaining budget is more than 0 but you have requested information,you can summarize your current findings and write the final technical research report."
        f"{task_injection}"
    )

    if not state.messages:
        user_content = f"متن خام خبر:\n{state.raw_text}"
        messages = [SystemMessage(content=system_instruction), HumanMessage(content=user_content)]
    else:
        # همیشه دستورالعمل سیستمی را با بودجه جدید بروزرسانی کرده و در ابتدای زنجیره پیام‌ها قرار می‌دهیم
        messages = [SystemMessage(content=system_instruction)] + [m for m in state.messages if
                                                                  not isinstance(m, SystemMessage)]

    response = llm.invoke(messages)

    # 🛑 سد دفاعی فیزیکی و برنامه‌نویسی‌شده جهت جلوگیری از وقوع تداخل بودجه و لوپ بی‌نهایت
    if remaining_budget <= 0 and hasattr(response, "tool_calls") and response.tool_calls:
        logger.warning("Search budget is fully exhausted but model attempted tool call. Stripping tool calls manually.")
        response.tool_calls = []

    research_results_summary = ""
    # بررسی خاتمه فرآیند تحقیق (مدل به جای تول‌کال، پاسخ متنی تولید کرده یا بودجه تمام شده است)
    if (not response.tool_calls or remaining_budget <= 0) and len(messages) > 2:
        research_results_summary = response.content
        logger.info("تحقیق متوالی در وب به اتمام رسید و گزارش نهایی آماده شد.")
        add_log_event(
            state.received_message_id,
            "RESEARCHER_COMPLETED",
            "گزارش گام‌به‌گام و تکاملی تحقیق وب با موفقیت نهایی شد.",
            {"summary": research_results_summary}
        )

    if api and api_key:
        try:
            api.increment_usage()
        except Exception:
            pass

    return {
        "messages": [response],
        "research_results": research_results_summary if research_results_summary else state.research_results
    }


def researcher_routing(state: WriterWorkflowState) -> Literal["tools", "writer"]:
    # شمارش مجدد برای هدایت شرطی دقیق
    tool_calls_made = 0
    for msg in state.messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls_made += len(msg.tool_calls)
    remaining_budget = 3 - tool_calls_made

    if remaining_budget > 0 and state.messages and state.messages[-1].tool_calls:
        add_log_event(
            state.received_message_id,
            "RESEARCHER_TOOL_CALL",
            f"درخواست سرچ زنجیره‌ای صادر شد. کوئری شماره {tool_calls_made + 1} به Tavily ارسال می‌شود."
        )
        return "tools"

    return "writer"


def writer_node(state: WriterWorkflowState) -> Dict[str, Any]:
    logger.info("اجرای نود نویسنده خلاق با لایه فال‌بک موازی و پویا...")

    medias_text = ""
    for m in state.medias_info:
        medias_text += f"- شناسه رسانه: {m['id']} | نوع: {m['type']} | توضیحات تحلیل‌شده: {m['description']} | متن جایگزین سئو: {m['alt_text']}\n"

    task_injection = ""
    if state.supervisor_task:
        task_injection = f"\n\n**دستورالعمل و تسک سردبیری ابلاغ شده:**\n{state.supervisor_task}\n"

    # واکشی پویا تاریخ جاری سیستم
    greg_date, jalali_date = get_current_dates()

    system_prompt = f"""
    You are the Executive Editor-in-Chief, Lead Conversion Copywriter, and Technical Journalist at "Teknovia" (تکنوویا).
    Your objective is to produce premium, highly-engaging, human-grade, and SEO-optimized technology articles and accompanying social media posts in Persian.

    You must strictly synthesize all incoming data (raw news, web summaries, research results, and media info) into a structured output matching the `WriterOutputSchema`.

    **CURRENT TEMPORAL SIGNAL (DO NOT HALLUCINATE TIME)**:
    - Gregorian Date: {greg_date}
    - Persian Jalali Date: {jalali_date}
    We are strictly operating in this year. Ensure your narratives, timelines, and insights align exactly with this context.

    {task_injection}

    ---

    ### 1. IMAGE CONSERVATION & SMART PLACEHOLDER LAW
    Creating images through text-to-image APIs is computationally expensive and pipeline-heavy. You must be extremely conservative with your recommendations.
    - **Rule of Existing Media Priority**: If the `medias_info` list contains high-quality existing images, you MUST prioritize using them for both the featured image (`featured_media`) and inline placements. Do NOT suggest new images if the existing ones are sufficient and relevant.
    - **Strict Suggestion Budget**: You are allowed a MAXIMUM of 1 (one) new image suggestion in `global_suggestions` under normal circumstances, and strictly capped at 2 (two) only for complex step-by-step guides. Never recommend generic, purely decorative image placeholders.
    - **Surgical Prompting**: For any suggested image, do not write a generic prompt. 
      - If it represents a real-world company, product, logo, or public figure, start the description exactly with: 
        `"Better search this image on the internet. Recommended query: [1 to 3 short keyword queries]"`
      - If it is abstract/artistic, write a clean English prompt. Ensure you append: `"no text, no letters, no typography, no words, clean visual representation"` to prevent gibberish text in generated images.

    #### Placement Syntax in Article Body:
    - **For existing images**: Use `![alt_text](media_id:ID)` (e.g., `![رونمایی از کنسول جدید](media_id:12)`).
    - **For newly suggested images**: You MUST use a custom, SEO-rich Persian alt text within standard markdown brackets, referencing your suggestion ID like this: `![custom_seo_persian_alt_text](suggestion_id:LOCAL_ID)`.
      - *Example*: `![تراشه شتاب‌دهنده هوش مصنوعی Blackwell انویدیا با معماری جدید](suggestion_id:1)`
      - This ensures our system can dynamically capture your custom alt text when the image is generated.

    ---

    ### 2. THE HUMANIZER PROTOCOL (ANTI-AI SLOP & SOUL INJECTION)
    Your writing must be indistinguishable from a seasoned, critical human tech journalist. Read your draft aloud internally—if it sounds like a textbook, press release, or standard chatbot, destroy it and rewrite.

    #### A. AI Vocabulary Blacklist (STRICTLY PROHIBITED)
    Never use these statistically over-generated AI words or their Persian equivalents:
    - *Additionally* (علاوه بر این / افزون بر این)
    - *Delve* (کاوش کردن / عمیق شدن)
    - *Enhance / Fostering / Cultivating* (بهبود بخشیدن / ترویج دادن / پرورش دادن)
    - *Landscape / Tapestry / Interplay* (چشم‌انداز / تار و پود / بازی متقابل)
    - *Pivotal / Crucial / Testament / Stands as* (محوری / حیاتی / گواهی بر / به عنوان ... عمل می‌کند)
    - *Underscore / Highlight / Showcase* (تاکید کردن / برجسته کردن / به نمایش گذاشتن)
    - *Vibrant / Breathtaking / Nestled / Stunning* (پرجنب‌وجوش / نفس‌گیر / واقع در قلب / خیره‌کننده)
    - *It is worth noting that* (شایان ذکر است / جالب است بدانید)
    - *In today's digital era / landscape* (در دنیای دیجیتال امروز / در عصر حاضر)

    #### B. Style & Grammar Guardrails
    - **Vary Your Rhythm**: Avoid monotonous sentence lengths. Mix very short, punchy statements with longer, explanatory thoughts to create natural reading energy.
    - **Avoid Copula Avoidance**: Do not use "serves as" (به عنوان ... عمل میکند) or "stands as". Use simple copulas ("is/are/has" - است / هستند / دارد).
    - **No Rule of Three Overuse**: Do not force concepts, benefits, or descriptions into artificial groups of three.
    - **Erase False Ranges**: Avoid meaningless "from X to Y" (از کهکشان‌ها گرفته تا ذرات اتمی) structures.
    - **Minimize Em-Dashes and Boldface**: Do not over-decorate or mechanically emphasize words. Use punctuation naturally.
    - **No Title Case in Subheadings**: Persian subheadings must follow normal, natural Persian sentence casing. No decorative emojis in headings.

    #### C. Inject Personality and Technical Skepticism
    - **Have logical opinions**: Do not just present sterile, neutral lists of pros and cons. If a new AI feature seems like useless marketing hype, say so with reasoned technical skepticism (e.g., "هرچند بنچمارک‌های آزمایشگاهی نوید جهش بزرگی را می‌دهند، اما در سناریوهای واقعی، چالش داغ شدن تراشه کماکان حل‌نشده باقی مانده است").
    - **Acknowledge Complexity**: Humans have mixed, nuanced feelings. Write with intellectual honesty.

    ---

    ### 3. SEO & CORE-EEAT CONTENT STRUCTURE
    You must structure the Persian article body (`content`) according to strict search-engine standards while offering genuine value:

    - **Strict Heading Hierarchy**: H1 (Title) -> H2 (Main sections) -> H3 (Subsections). Never skip header levels (e.g., H2 directly to H4 is illegal).
    - **GEO-Optimized Direct Answer**: In the first 100-150 words of the article, provide a highly clear, direct, and factual 40-60 word definition or answer to the primary topic. This is critical for Google Featured Snippets.
    - **High Information Density (FACTUAL ACCURACY FIRST)**:
      - Do NOT invent, assume, or hallucinate any numbers, statistics, or pricing.
      - High information density means *preserving* and cleanly presenting every single real specification, measurement, standard, or price that is actually present in the source materials without diluting them with fluff or filler words.

    ---

    ### 4. TELEGRAM POST SPECIFICATIONS
    The social media post (`post`) must be highly scannable and written in Persian Markdown.
    - **Hook-First**: Front-load the hook in the first 120 characters. Grab attention immediately.
    - **Strict Link Placeholder**: Since the final website URL is generated after publishing, you MUST use the exact placeholder `<!-- MAIN_ARTICLE_URL -->` once inside the post text as the primary call-to-action link.
    - **No Emojis Flooding**: Limit emojis to 1 or 2 per post max. Do not decorate bullet points with emojis.

    ---

    ### 5. ANALYTICAL WORKFLOW BEFORE WRITING
    1. **Analyze Input**: Read the raw text, summaries, and research findings. Identify the core news angle.
    2. **Review Media**: Check `medias_info`. If you can use existing images for the featured cover and inside the text, do so. Do not recommend new ones unless absolutely necessary.
    3. **Draft the Article**: Focus on direct answers, strict heading hierarchy, natural transitions, zero AI-isms, and strong technical opinions. Use the `suggestion_id` syntax for the suggested images.
    4. **Draft the Telegram Post**: Build a short, high-conversion post with the required URL placeholder.
    """

    user_prompt = f"""
    متن خام ورودی:
    {state.raw_text}

    محتوای وب لینک‌های استخراج شده:
    {state.links_content}

    رسانه‌های موجود در سیستم (شناسه‌ها و تحلیل‌ها):
    {medias_text if medias_text else 'هیچ رسانه‌ای متصل نیست.'}

    گزارش دقیق تحقیق وب (کمکی):
    {state.research_results or 'تحقیق وب انجام نشده است.'}
    """

    # لیست ترتیبی مدل‌ها برای اجرای مکانیزم فال‌بک حرفه‌ای
    models_to_try = [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite"
    ]

    writer_output = None
    success = False
    last_error = ""

    api = ApiContainer.objects.filter(status=True, provider__in=["gemini", "google"]).order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("GEMINI_API_KEY")

    if api_key:
        for model_name in models_to_try:
            if success:
                break

            logger.info(f"Attempting to generate article using model: {model_name}")

            # ۵ تلاش مجدد برای هر مدل در صورت بروز خطا
            for attempt in range(1, 6):
                try:
                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        api_key=SecretStr(api_key),
                        thinking_level="high",  # فعال‌سازی قابلیت تفکر عمیق بومی برای تمامی سری‌های جمینای ۳
                        timeout=150
                    ).with_structured_output(WriterOutputSchema)

                    response = llm.invoke([
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt)
                    ])

                    writer_output = response
                    success = True
                    logger.info(f"Successfully generated article using {model_name} on attempt {attempt}")
                    add_log_event(
                        state.received_message_id,
                        "WRITER_SUCCESS",
                        f"نگارش سردبیری با مدل {model_name} در تلاش {attempt} با موفقیت انجام شد."
                    )
                    break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Model {model_name} failed on attempt {attempt}: {e}")
                    # تاخیر فزاینده فایده‌بخش برای آزادسازی قفل‌های ریت‌لیمیت دیتابیسی
                    time.sleep(2.0 * attempt)

        if not success:
            logger.error(f"All model fallbacks failed. Last error: {last_error}")
            add_log_event(
                state.received_message_id,
                "WRITER_ERROR_ALL_MODELS",
                f"تمام مدل‌های نگارش به دلیل خطاهای شبکه یا محدودیت نرخ درخواست شکست خوردند. آخرین خطا: {last_error}"
            )
            # ایجاد یک خروجی فال‌بک پیش‌فرض امن جهت جلوگیری از فریز شدن گراف
            writer_output = WriterOutputSchema(
                skip=True,
                skip_reason="تمام تلاش‌های سیستم فال‌بک با خطا مواجه شد."
            )
    else:
        logger.error("No Gemini API key found for writer workflow fallbacks.")
        writer_output = WriterOutputSchema(
            skip=True,
            skip_reason="کلید ارتباطی وب‌سرویس گوگل یافت نشد."
        )

    if api and success:
        try:
            api.increment_usage()
        except Exception:
            pass

    return {"writer_output": writer_output}


def saver_node(state: WriterWorkflowState) -> Dict[str, Any]:
    logger.info("اجرای نود نهایی ذخیره و انتشار خودکار...")

    message_id = state.received_message_id
    writer_output = state.writer_output

    if not writer_output:
        logger.error(f"پاسخی از نویسنده برای پیام {message_id} ثبت نشده است.")
        return {}

    try:
        msg = ReceivedMessages.objects.get(id=message_id)
    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages با شناسه {message_id} یافت نشد.")
        return {}

    if writer_output.skip:
        msg.is_finished = True
        msg.step = ReceivedMessages.Steps.FINISHED
        msg.save()
        logger.info(f"پیام {message_id} اسکیپ شد. علت: {writer_output.skip_reason}")
        add_log_event(message_id, "SAVER_SKIPPED",
                      f"خبر ورودی طبق تحلیل سردبیر ارزش خبرگزاری نداشت. علت: {writer_output.skip_reason}")
        finalize_log(message_id, WorkflowLog.StatusChoices.SKIPPED)
        return {}

    global_suggestions = writer_output.global_suggestions or []
    article_suggestions_list = []
    post_suggestions_list = []

    for sug in global_suggestions:
        unique_tracking_id = str(uuid.uuid4())
        suggestion_payload = {
            "tracking_id": unique_tracking_id,
            "local_id": sug.id,
            "prompt": sug.prompt_or_description,
            "placements": sug.placements,
            "inline_position": sug.inline_position,
            "message_id": message_id
        }

        if any(p in sug.placements for p in ["article_featured", "article_inline"]):
            article_suggestions_list.append(suggestion_payload)

        if "telegram_post" in sug.placements:
            post_suggestions_list.append(suggestion_payload)

    created_content_obj = None
    article_data = writer_output.article

    if article_data:
        try:
            content_obj = Content.objects.create(
                title=article_data.title,
                summary=article_data.summary,
                content=article_data.content,
                importance=article_data.importance,
                schema_type=article_data.type,
                indexable=article_data.indexable,
                status=Content.StatusChoices.DRAFT,
                suggestions=article_suggestions_list if article_suggestions_list else None,
                suggestions_status=Content.Suggestions.WAITING if article_suggestions_list else Content.Suggestions.EMPTY,
                author=settings.SITE_NAME,
                data_source=msg
            )
            created_content_obj = content_obj
            logger.info(f"پیش‌نویس جدید مقاله وب‌سایت ایجاد شد (Content ID={content_obj.id})")
            add_log_event(
                message_id,
                "SAVER_ARTICLE",
                f"مقاله جدید وب‌سایت به شکل پیش‌نویس (Draft) ذخیره شد. شناسه: {content_obj.id}"
            )

            # زنجیره‌سازی خودکار به فرآیند سئو بدون بروز تداخل دورانی ایمپورت‌ها
            try:
                from celery import current_app
                current_app.send_task("workflows.tasks.process_seo_workflow", args=[content_obj.id])
                logger.info(f"محتوای جدید {content_obj.id} جهت انجام بهینه‌سازی‌های سئو به تسک سلری فرستاده شد.")
            except Exception as celery_e:
                logger.error(f"Error triggering SEO task for content {content_obj.id}: {celery_e}")

            used_images = article_data.used_images or []
            if used_images:
                featured_id = article_data.featured_media or used_images[0]
                featured_media = MediaContainer.objects.filter(id=featured_id).first()
                if featured_media:
                    content_obj.featured_media = featured_media
                    content_obj.save()
                MediaContainer.objects.filter(id__in=used_images).update(is_used=True)

        except Exception as e:
            logger.error(f"خطا در ایجاد رکورد Content در جنگو: {e}", exc_info=True)
            add_log_event(message_id, "SAVER_ARTICLE_ERROR", f"خطا در ذخیره‌سازی محتوای سایت: {str(e)}")

    post_data = writer_output.post
    if post_data:
        try:
            has_tg_suggestions = len(post_suggestions_list) > 0

            post_obj = PostsContainer.objects.create(
                content=post_data.content,
                main_article=created_content_obj,
                state=PostsContainer.State.DRAFT,
                suggestions=post_suggestions_list if post_suggestions_list else None,
                suggestions_status=PostsContainer.Suggestions.WAITING if post_suggestions_list else PostsContainer.Suggestions.EMPTY,
                data_source=msg
            )
            add_log_event(
                message_id,
                "SAVER_POST",
                f"پست جدید شبکه‌های اجتماعی ایجاد شد. شناسه: {post_obj.id} | وضعیت: پیش‌نویس"
            )

            selected_medias = post_data.selected_medias or []
            if selected_medias:
                post_obj.medias.add(*selected_medias)
                MediaContainer.objects.filter(id__in=selected_medias).update(is_used=True)

            # اگر پست تلگرام نیازی به ساخت تصاویر جدید ندارد، مستقیماً به تسک متمرکز انتشار فرستاده می‌شود
            if not has_tg_suggestions:
                try:
                    from celery import current_app
                    current_app.send_task("workflows.tasks.process_publisher_workflow", args=[post_obj.id])
                    logger.info(f"پست تلگرام {post_obj.id} نیازی به تصویرساز نداشت؛ فرستاده شد به تسک انتشار.")
                except Exception as celery_e:
                    logger.error(f"Error triggering publisher task for post {post_obj.id}: {celery_e}")

        except Exception as e:
            logger.error(f"خطا در ایجاد رکورد PostsContainer در دیتابیس: {e}", exc_info=True)
            add_log_event(message_id, "SAVER_POST_ERROR", f"خطا در ایجاد پست در دیتابیس: {str(e)}")

    try:
        msg.is_finished = True
        msg.step = ReceivedMessages.Steps.FINISHED
        msg.save()
        logger.info(f"کل فرآیند نگارش و سازماندهی پیام دریافتی {message_id} خاتمه یافت.")
        add_log_event(message_id, "COMPLETED", "کل فرآیند اجرای زنجیره پردازش و نگارش با موفقیت به پایان رسید.")
        finalize_log(message_id, WorkflowLog.StatusChoices.COMPLETED)
    except Exception as e:
        logger.error(f"خطا در نهایی‌سازی گام ReceivedMessage: {e}")

    return {}


# ────────────────────────────────────────────────────────────────
# پیکربندی نهایی گراف لنگ‌چین (Graph Compilation)
# ────────────────────────────────────────────────────────────────

tool_node = ToolNode([search_web_for_news])


def get_writer_graph():
    """
    ساخت، سازماندهی و کامپایل نهایی گراف سردبیری و نگارش محتوا
    """
    workflow = StateGraph(WriterWorkflowState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("saver", saver_node)

    workflow.add_edge(START, "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        supervisor_routing,
        {
            "researcher": "researcher",
            "saver": "saver",
            "writer": "writer"
        }
    )

    workflow.add_conditional_edges(
        "researcher",
        researcher_routing,
        {
            "tools": "tools",
            "writer": "writer"
        }
    )

    workflow.add_edge("tools", "researcher")
    workflow.add_edge("writer", "saver")
    workflow.add_edge("saver", END)

    return workflow.compile()
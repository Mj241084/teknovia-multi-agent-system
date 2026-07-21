import os
import logging
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, SecretStr
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from django.conf import settings
from contents.models import Content, Category, Tag
from accounts.models import ApiContainer
from workflows.logging_services import add_log_event

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# متدهای کمکی جهت مدل‌سازی ساختار درختی دسته‌بندی‌ها به همراه توضیحات موضوعی
# ────────────────────────────────────────────────────────────────

def format_categories_as_tree(categories: List[Category], parent: Optional[Category] = None, indent: str = "") -> str:
    """
    تولید ساختار درختی دایرکتوری‌مانند (Markdown-based Folder Tree) از دسته‌بندی‌های فعال سیستم.
    این تابع توضیحات موضوعی هر دسته‌بندی را نیز به درخت پیوست می‌کند تا هوش مصنوعی قلمرو موضوعی هر شاخه را درک کند.
    """
    tree_str = ""
    level_cats = [c for c in categories if c.parent == parent]

    # مرتب‌سازی بر اساس فیلد ترتیب و نام
    level_cats.sort(key=lambda x: (x.order, x.name))

    for idx, cat in enumerate(level_cats):
        is_last = (idx == len(level_cats) - 1)
        connector = "└── " if is_last else "├── "
        desc_str = f" [توضیحات محدوده موضوعی: {cat.description}]" if cat.description else ""
        tree_str += f"{indent}{connector}{cat.name} (شناسه دسته‌بندی: {cat.id}){desc_str}\n"

        # پیشروی بازگشتی به گام فرزندان
        next_indent = indent + ("    " if is_last else "│   ")
        tree_str += format_categories_as_tree(categories, parent=cat, indent=next_indent)

    return tree_str


# ────────────────────────────────────────────────────────────────
# ساختارهای وضعیت Pydantic (Pydantic Workflow States)
# ────────────────────────────────────────────────────────────────

class SeoWorkflowState(BaseModel):
    content_id: int
    message_id: int = 0
    title: str = ""
    summary: str = ""
    content_text: str = ""
    selected_category_ids: List[int] = []
    selected_tags: List[str] = []
    meta_title: str = ""
    meta_description: str = ""
    slug: str = ""


# ────────────────────────────────────────────────────────────────
# الگوهای ساختار یافته خروجی مدل (LLM Structured Schemas)
# ────────────────────────────────────────────────────────────────

class SeoAnalysisOutput(BaseModel):
    selected_category_ids: List[int] = Field(
        description=(
            "List of Category IDs that perfectly fit this article. "
            "CRITICAL LIMIT: Select between 1 to 3 categories ONLY. "
            "Strictly choose from the tree hierarchy provided."
        )
    )
    existing_tags_to_keep: List[str] = Field(
        description="List of tag names from the provided existing tags that are relevant to this article. Choose up to 5."
    )
    new_tags_to_create: List[str] = Field(
        description=(
            "List of new Persian tags (max 5) that are highly relevant to this article. "
            "Ensure they are optimized for search queries, have no typos, no verbs, and no special symbols."
        )
    )
    meta_title: str = Field(
        description="An optimized, catchy Persian meta title for search engines (under 70 characters)."
    )
    meta_description: str = Field(
        description="An optimized, concise Persian meta description summarizing the core value of the article (under 160 characters)."
    )
    slug: str = Field(
        description="An SEO-friendly Persian slug derived from the title or primary keywords. Replace spaces with hyphens (-) and do not use special characters."
    )


# ────────────────────────────────────────────────────────────────
# پیاده‌سازی گام‌به‌گام نودها (Nodes Implementation)
# ────────────────────────────────────────────────────────────────

def seo_analyzer_node(state: SeoWorkflowState) -> Dict[str, Any]:
    """
    نود آنالیز و استخراج خودکار سئو و معماری محتوا با استفاده از جمینای
    """
    logger.info(f"شروع آنالیز سئو برای مقاله شناسه {state.content_id}...")

    # ۱. واکشی دسته‌بندی‌های فعال سیستم جهت تولید درخت ساختاریافته به همراه توضیحات
    categories_qs = list(Category.objects.filter(is_active=True))
    categories_tree_str = format_categories_as_tree(categories_qs)

    # ۲. واکشی برچسب‌های پرکاربرد دیتابیس بومی جهت تطابق
    tags_qs = Tag.objects.all().order_by('-id')[:500]
    existing_tags = [t.name for t in tags_qs]
    tags_list_str = ", ".join(existing_tags) if existing_tags else "هیچ برچسبی وجود ندارد."

    system_instruction = (
        "You are the Senior SEO and Taxonomy Architect."
        "Your objective is to analyze a newly generated technology article and integrate it perfectly into our site's directory hierarchy and tag taxonomy, while producing high-conversion search metadata (Meta Title, Meta Description, and SEO Slug).\n\n"

        "CRITICAL TAXONOMY AND INHERITANCE RULES:\n"
        "1. CATEGORY BOUNDS: You MUST select between 1 to 3 categories ONLY (Minimum 1, Maximum 3).\n"
        "2. THEMATIC PRIORITY: Your selection must be guided strictly by thematic and semantic similarity. Do NOT force a child category selection if the main parent category represents the article's core theme more accurately. Selecting a main category is fully valid if the topic is broad.\n"
        "3. INHERITANCE CONCEPT: Assigning an article to a child category automatically implies that the article belongs to the parent category in our database and frontend. Therefore, do NOT assign both a parent category and its child category to the same article. Doing so wastes your category budget.\n"
        "4. SCOPE VERIFICATION: Read the provided description for each category carefully to map the article to the most appropriate level of our taxonomy.\n"
        "5. TAG LIMITS: The total number of tags selected (existing tags + newly created tags) MUST be between 2 to 5 tags ONLY (Minimum 2, Maximum 5).\n"
        "6. TAG RULES: New tags must be written in clean Persian, must be nouns, must not contain verbs, "
        "must not contain special characters, and must be optimized for search engine traffic."
    )

    user_content = f"""
    عنوان مقاله: {state.title}
    خلاصه مقاله: {state.summary}
    متن مقاله: {state.content_text[:2000]}

    --------------------------------------------------
    درخت و ساختار پوشه‌ای دسته‌بندی‌های موجود در سیستم (شناسه‌ها، ساختار و توضیحات موضوعی):
    {categories_tree_str}

    --------------------------------------------------
    لیست برچسب‌های (Tags) موجود در سیستم جهت تطابق:
    {tags_list_str}
    """

    api = ApiContainer.objects.filter(status=True, provider__in=["gemini", "google"]).order_by('today_use', '?').first()
    api_key = api.key if api else os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.error("No Gemini API key found for SEO workflow.")
        return {}

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash-lite",
            api_key=SecretStr(api_key),
            thinking_level="high"
        ).with_structured_output(SeoAnalysisOutput)

        response = llm.invoke([
            SystemMessage(content=system_instruction),
            HumanMessage(content=user_content)
        ])

        # مهار محدوده تگ‌ها طبق الگو
        all_tags = list(set(response.existing_tags_to_keep + response.new_tags_to_create))
        all_tags = all_tags[:5]  # سقف مطلق ۵ تگ

        # تضمین حداقل ۲ تگ در خروجی
        if len(all_tags) < 2:
            all_tags.append("تکنولوژی")
            all_tags.append("هوش مصنوعی")
            all_tags = list(set(all_tags))[:5]

        # مهار محدوده دسته‌بندی‌ها
        selected_cats = response.selected_category_ids[:3]
        if not selected_cats:
            first_cat = Category.objects.filter(is_active=True).first()
            if first_cat:
                selected_cats = [first_cat.id]

        if api:
            try:
                api.increment_usage()
            except Exception:
                pass

        return {
            "selected_category_ids": selected_cats,
            "selected_tags": all_tags,
            "meta_title": response.meta_title,
            "meta_description": response.meta_description,
            "slug": response.slug
        }

    except Exception as e:
        logger.error(f"Error executing SEO LLM node: {e}", exc_info=True)
        return {}


def seo_saver_node(state: SeoWorkflowState) -> Dict[str, Any]:
    """
    اعمال نهایی تغییرات سئو، دسته‌بندی و برچسب‌ها در پایگاه‌داده جنگو بر پایه رابطه چندبه‌چند بومی
    """
    logger.info(f"در حال اعمال ذخیره‌سازی داده‌های سئو بر روی دیتابیس برای مقاله {state.content_id}...")

    try:
        content_obj = Content.objects.get(id=state.content_id)

        # بروزرسانی فیلدهای فراداده سئو
        content_obj.meta_title = state.meta_title[:70] if state.meta_title else content_obj.title[:70]
        content_obj.meta_description = state.meta_description[:160] if state.meta_description else content_obj.summary[:160]

        # تصحیح و استانداردسازی اسلاگ فارسی
        if state.slug:
            clean_slug = state.slug.replace(" ", "-").replace("/", "-")
            content_obj.slug = clean_slug[:200]

        # اصلاح و همگام‌سازی کامل با روت جدید فرانت‌انداسترو (تغییر از /news/ به /post/) جهت کارایی سئو
        site_url = getattr(settings, 'SITE_URL', 'https://teknovia.ir').rstrip('/')
        content_obj.canonical_url = f"{site_url}/post/{content_obj.slug}/"

        # فعال کردن ایندکس بومی برای موتورهای جستجو
        content_obj.indexable = True
        content_obj.save()

        # برقراری ارتباط‌های چند به چند (ManyToMany) دسته‌بندی‌ها
        if state.selected_category_ids:
            content_obj.category.set(state.selected_category_ids)
            logger.info(f"مقاله {state.content_id} به دسته‌بندی‌های {state.selected_category_ids} متصل شد.")

        # ساخت، واکشی و همگام‌سازی کامل تگ‌های بومی به شکل کاملاً تراکنشی و همزمان
        if state.selected_tags:
            clean_tags = [t.strip() for t in state.selected_tags if t and t.strip()]
            tag_instances = []

            for t_name in clean_tags:
                from django.utils.text import slugify
                slug = slugify(t_name, allow_unicode=True)

                # استفاده از متد ایمن و اتمیک get_or_create جهت جلوگیری از رخداد تداخلی
                tag_obj, _ = Tag.objects.get_or_create(
                    name=t_name,
                    defaults={'slug': slug}
                )
                tag_instances.append(tag_obj)

            # پیوند زدن دسته‌جمعی برچسب‌های بومی جدید به مقاله
            content_obj.tags.set(tag_instances)
            logger.info(f"تعداد {len(tag_instances)} برچسب بومی به مقاله {state.content_id} متصل شد.")

        # ثبت گزارش موفقیت در لاگ سراسری فرآیند پیام مرجع
        if state.message_id:
            add_log_event(
                state.message_id,
                "SEO_OPTIMIZED",
                f"بهینه‌سازی سئو با موفقیت اعمال شد. عنوان متا: {content_obj.meta_title} | تعداد تگ‌ها: {content_obj.tags.count()}"
            )

    except Content.DoesNotExist:
        logger.error(f"Content with ID {state.content_id} not found during SEO saving.")
    except Exception as e:
        logger.error(f"Error saving SEO outputs: {e}", exc_info=True)
        if state.message_id:
            add_log_event(state.message_id, "SEO_ERROR", f"خطا در زمان اعمال فیزیکی بهینه‌سازی سئو: {str(e)}")

    return {}


# ────────────────────────────────────────────────────────────────
# ساخت، تعریف و کامپایل گراف سئو (Graph Compilation)
# ────────────────────────────────────────────────────────────────

def get_seo_workflow_graph():
    """
    ساخت و کامپایل گراف پردازش سئو، برچسب‌ها و متادیتاهای مقاله
    """
    workflow = StateGraph(SeoWorkflowState)
    workflow.add_node("analyzer", seo_analyzer_node)
    workflow.add_node("saver", seo_saver_node)

    workflow.add_edge(START, "analyzer")
    workflow.add_edge("analyzer", "saver")
    workflow.add_edge("saver", END)

    return workflow.compile()
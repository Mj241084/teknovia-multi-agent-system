# /var/www/teknovia/AI-Agency/workflows/publisher_workflow.py
import os
import io
import re
import html
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from telethon import TelegramClient
from telethon.sessions import StringSession
from asgiref.sync import async_to_sync

from django.conf import settings
from django.utils import timezone
from contents.models import Content, MediaContainer, PostsContainer
from workflows.logging_services import add_log_event, finalize_log
from workflows.models import WorkflowLog

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# توابع کمکی تبدیل مارک‌داون به HTML تلگرام و آدرس کانونیکال
# ────────────────────────────────────────────────────────────────

def get_article_absolute_url(article: Optional[Content]) -> str:
    """
    تولید لینک کامل و کانونیکال مقاله در فرانت‌اند آسترو بر پایه روت نوین /post/ و دامنه جدید تکنوویا
    """
    if not article:
        return ""

    frontend_url = getattr(settings, 'FRONTEND_URL', 'https://teknovia.ir').rstrip('/')
    return f"{frontend_url}/post/{article.slug}/"


def replace_article_url_placeholder(markdown_text: str, article: Optional[Content]) -> str:
    """
    جای‌گذاری لینک واقعی مقاله اصلی به جای تگ نگهدارنده <!-- MAIN_ARTICLE_URL -->
    به همراه پوشش هایپرلینک پشت متن
    """
    if not markdown_text:
        return ""

    article_url = get_article_absolute_url(article)
    placeholder = "<!-- MAIN_ARTICLE_URL -->"
    hyperlink_text = f"[جزئیات بیشتر...]({article_url})"

    return markdown_text.replace(placeholder, hyperlink_text)


def markdown_to_telegram_html(text: str) -> str:
    """
    تبدیل متن مارک‌داون به فرمت HTML استاندارد قابل پشتیبانی در تلگرام (Telethon HTML Mode)
    """
    if not text:
        return ""

    # ۱. فرار دادن کاراکترهای خطرناک HTML
    text = html.escape(text)

    # ۲. تبدیل کد بلوک سه‌تایی ```code``` به <pre>code</pre>
    def re_code_block(match):
        code_content = match.group(1).strip()
        return f"<pre>{code_content}</pre>"

    text = re.sub(r"```(?:\w+)?\n?(.*?)```", re_code_block, text, flags=re.DOTALL)

    # ۳. تبدیل تک کد inline `code` به <code>code</code>
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # ۴. تبدیل لینک‌های مارک‌داون [text](url) به <a href="url">text</a> (بهینه‌شده برای آدرس‌های حاوی کاراکترهای فارسی)
    def re_link(match):
        link_text = match.group(1)
        link_url = html.unescape(match.group(2))
        return f'<a href="{link_url}">{link_text}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", re_link, text)

    # ۵. تبدیل بولد **text** یا __text__ به <b>text</b>
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)

    # ۶. تبدیل ایتالیک *text* یا _text_ به <i>text</i>
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"_([^_]+)_", r"<i>\1</i>", text)

    # ۷. تبدیل تیترهای مارک‌داون (# Heading -> <b>Heading</b>)
    text = re.sub(r"^#{1,6}\s+(.*)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    return text


# ────────────────────────────────────────────────────────────────
# توابع ناهمگام Telethon مجهز به ساختار محافظتی Timeout و لایه مستقل نخ
# ────────────────────────────────────────────────────────────────

async def send_to_telegram_async(channel_id: str, text: str, media_containers: List[MediaContainer]) -> bool:
    """
    ارسال ناهمگام پیام و رسانه‌ها به کانال تلگرام با فرمت‌بندی HTML استاندارد و مجهز به حد زمانی برای عدم فریز
    """
    async def _send():
        app_id = getattr(settings, 'TELEGRAM_APP_ID', None)
        app_hash = getattr(settings, 'TELEGRAM_APP_HASH', None)
        session_str = getattr(settings, 'TELEGRAM_SESSION', None)

        if not app_id or not app_hash or not session_str:
            logger.error("تنظیمات ارتباطی تلگرام در تنظیمات پروژه تکمیل نشده است.")
            return False

        client = TelegramClient(StringSession(session_str), int(app_id), app_hash)
        await client.connect()

        if not await client.is_user_authorized():
            logger.error("نشست کاربری تله‌تون معتبر نیست؛ امکان ارسال پیام وجود ندارد.")
            await client.disconnect()
            return False

        files_to_send = []
        opened_files = []

        for container in media_containers:
            if container.media:
                try:
                    container.media.open('rb')
                    file_bytes = container.media.read()
                    opened_files.append(container.media)

                    filename = os.path.basename(container.media.name)
                    file_like = io.BytesIO(file_bytes)
                    file_like.name = filename

                    files_to_send.append(file_like)
                except Exception as ex:
                    logger.error(f"خطا در آماده‌سازی باینری رسانه {container.id}: {ex}")

        try:
            entity = int(channel_id)
        except ValueError:
            entity = channel_id

        if files_to_send:
            await client.send_file(entity, files_to_send, caption=text, parse_mode='html')
        else:
            await client.send_message(entity, text, parse_mode='html')

        for f in opened_files:
            try:
                f.close()
            except Exception:
                pass

        await client.disconnect()
        return True

    try:
        # محافظت از فریز شدن کانتینر با ایجاد سقف ۶۰ ثانیه‌ای برای ارسال
        return await asyncio.wait_for(_send(), timeout=60.0)
    except asyncio.TimeoutError:
        logger.error("ارسال پیام به تلگرام به دلیل سپری شدن مهلت ۶۰ ثانیه‌ای لغو شد.")
        return False
    except Exception as e:
        logger.error(f"خطا در اجرای فرآیند ارسال Telethon به کانال: {e}", exc_info=True)
        return False


def send_to_telegram_sync(channel_id: str, text: str, media_containers: List[MediaContainer]) -> bool:
    """
    واسط همگام برای فراخوانی تابع ناهمگام تله‌تون با ساخت حلقه رویداد تازه جهت عدم تداخل با سلری
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(send_to_telegram_async(channel_id, text, media_containers))
    except Exception as e:
        logger.error(f"خطا در ارتباط حلقه رویداد مستقل با تله‌تون: {e}", exc_info=True)
        try:
            return async_to_sync(send_to_telegram_async)(channel_id, text, media_containers)
        except Exception as e2:
            logger.error(f"روش کمکی دوم async_to_sync نیز با خطا مواجه شد: {e2}", exc_info=True)
            return False
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────
# تعریف وضعیت و نودهای ورک‌فلوی انتشار (Publisher Workflow)
# ────────────────────────────────────────────────────────────────

class PublisherWorkflowState(BaseModel):
    post_id: int
    message_id: int = 0
    article_id: Optional[int] = None
    is_published: bool = False
    is_sent_to_telegram: bool = False


def article_publisher_node(state: PublisherWorkflowState) -> Dict[str, Any]:
    """
    نود انتشار مقاله وب‌سایت: تغییر وضعیت مقاله اصلی از DRAFT به PUBLISHED، تنظیم تاریخ انتشار
    و در نهایت، تولید امبدینگ و ثبت رسمی سند در مجموعه contents دیتابیس برداری TurboVec.
    """
    logger.info(f"اجرای نود انتشار مقاله وب‌سایت برای پست {state.post_id}...")

    try:
        post = PostsContainer.objects.get(id=state.post_id)
        article = post.main_article

        if article:
            # ۱. انتشار رسمی مقاله در دیتابیس جنگو
            article.status = Content.StatusChoices.PUBLISHED
            if not article.publish_date:
                article.publish_date = timezone.now()
            article.save(update_fields=['status', 'publish_date'])

            logger.info(f"مقاله {article.id} با موفقیت در وب‌سایت منتشر شد (PUBLISHED).")
            if state.message_id:
                add_log_event(state.message_id, "ARTICLE_PUBLISHED", f"مقاله وب‌سایت #{article.id} با موفقیت منتشر شد.")

            # ۲. ایجاد امبدینگ متنی و ذخیره‌سازی در دیتابیس برداری TurboVec
            try:
                from workflows.vector_services import generate_text_embedding, add_document_to_vector_index

                # آماده‌سازی ساختاریافته متن برای تولید بردار معنایی
                text_to_embed = f"Title: {article.title}\nContent:\n{article.content}"
                vector = generate_text_embedding(text_to_embed)

                if vector:
                    # تنظیم باینری امبدینگ در دیتابیس محلی
                    article.set_embedding(vector)

                    # درج فیزیکی در FastAPI برداری TurboVec (مجموعه contents)
                    external_id = add_document_to_vector_index(
                        collection_name=settings.CONTENTS,
                        django_id=article.id,
                        vector=vector
                    )

                    if external_id is not None:
                        article.external_id = external_id
                        article.save(update_fields=['external_id', 'embedding_data'])
                        logger.info(
                            f"مقاله {article.id} با موفقیت در TurboVec (مجموعه {settings.CONTENTS}) با شناسه خارجی {external_id} ایندکس شد.")
                        if state.message_id:
                            add_log_event(state.message_id, "ARTICLE_INDEXED",
                                          f"بردار معنایی مقاله با موفقیت تولید و با شناسه خارجی {external_id} در TurboVec ثبت گردید.")
                    else:
                        article.save(update_fields=['embedding_data'])
                        logger.warning(f"امبدینگ مقاله {article.id} تولید شد اما شناسه خارجی از TurboVec دریافت نشد.")
                        if state.message_id:
                            add_log_event(state.message_id, "ARTICLE_INDEX_WARNING",
                                          "بردار مقاله تولید شد اما شناسه خارجی از TurboVec دریافت نشد.")
                else:
                    logger.error(f"تولید امبدینگ برای مقاله {article.id} با شکست مواجه شد.")
                    if state.message_id:
                        add_log_event(state.message_id, "ARTICLE_INDEX_ERROR",
                                      "سیستم موفق به تولید بردار متنی برای مقاله نشد.")
            except Exception as vec_err:
                logger.error(f"خطای سیستمی در فرآیند تولید و ثبت بردار مقاله {article.id}: {vec_err}", exc_info=True)
                if state.message_id:
                    add_log_event(state.message_id, "ARTICLE_INDEX_ERROR",
                                  f"بروز خطای استثنا در زمان همگام‌سازی برداری: {str(vec_err)}")

            return {"article_id": article.id, "is_published": True}

    except PostsContainer.DoesNotExist:
        logger.error(f"PostsContainer with ID {state.post_id} not found in article_publisher_node.")
    except Exception as e:
        logger.error(f"Error publishing article for post {state.post_id}: {e}", exc_info=True)

    return {"is_published": False}


def telegram_publisher_node(state: PublisherWorkflowState) -> Dict[str, Any]:
    """
    نود انتشار تلگرام: جای‌گذاری هوشمند لینک مقاله بر پایه اولویت‌های سه‌گانه،
    تبدیل خودکار برچسب‌ها به هشتگ و ارسال نهایی با Telethon.
    """
    logger.info(f"اجرای نود انتشار فیزیکی پست تلگرام #{state.post_id}...")

    try:
        post = PostsContainer.objects.get(id=state.post_id)

        if post.state == PostsContainer.State.SENT:
            logger.info(f"پست تلگرامی #{post.id} قبلاً ارسال شده است.")
            return {"is_sent_to_telegram": True}

        channel_id = getattr(settings, 'TELEGRAM_CHANNEL_ID', None)
        if not channel_id:
            logger.error("TELEGRAM_CHANNEL_ID در تنظیمات دیتابیس یا .env تعریف نشده است.")
            if state.message_id:
                add_log_event(state.message_id, "TELEGRAM_PUBLISH_FAILED", "can't find channel id.")
            return {"is_sent_to_telegram": False}

        raw_markdown_content = post.content or ""
        placeholder = "<!-- MAIN_ARTICLE_URL -->"
        channel_username = getattr(settings, 'TELEGRAM_CHANNEL_USERNAME', '@teknovia_ir')
        article = post.main_article

        content_processed = raw_markdown_content

        # ۱. پیاده‌سازی منطق سه‌گانه و هوشمند مدیریت لینک‌ها به صورت هایپرلینک پشت متن
        if article:
            article_url = get_article_absolute_url(article)
            hyperlink_text = f"[جزئیات بیشتر...]({article_url})"

            if placeholder in content_processed:
                # اولویت اول: قرار گرفتن در محل مشخص شده توسط نویسنده
                content_processed = content_processed.replace(placeholder, hyperlink_text)
            else:
                # اولویت دوم: الصاق خودکار به انتهای پیام به شکل هایپرلینک شیک
                content_processed += f"\n\n🔗 {hyperlink_text}"
        else:
            # اولویت سوم: نبود مقاله مرتبط (پست خالی) -> هیچ لینکی الصاق نمی‌شود و هولدر حذف می‌شود
            content_processed = content_processed.replace(placeholder, "")

        # ۲. اضافه کردن آیدی کانال تلگرام به انتهای پیام
        content_processed += f"\n\n🆔 {channel_username}"

        # ۳. تبدیل داینامیک برچسب‌های مقاله به هشتگ بر پایه اسلاگ بومی (Slug) بدون تغییر کاراکترهای خط تیره
        if article:
            tags_list = list(article.tags.all())
            if tags_list:
                hashtags = []
                for t in tags_list:
                    # فراخوانی مستقیم اسلاگ بدون تغییر خط تیره‌ها (مانند #کارت-گرافیک)
                    slug_cleaned = t.slug.strip() if t.slug else ""
                    if slug_cleaned:
                        slug_cleaned = slug_cleaned.replace('-', '_')
                        hashtags.append(f"#{slug_cleaned}")

                # الصاق هشتگ‌ها با فاصله در خط پایانی پیام
                if hashtags:
                    content_processed += "\n" + " ".join(hashtags)

        # ۴. تبدیل مارک‌داون پردازش‌شده به فرمت HTML اختصاصی تلگرام
        formatted_telegram_html = markdown_to_telegram_html(content_processed)

        # ۵. ارسال فیزیکی به کانال تلگرام به همراه رسانه‌های متصل
        media_list = list(post.medias.all())
        success = send_to_telegram_sync(channel_id, formatted_telegram_html, media_list)

        if success:
            post.state = PostsContainer.State.SENT
            post.sent_at = timezone.now()
            post.save()

            logger.info(f"پست تلگرام #{post.id} با موفقیت به کانال ارسال شد.")
            if state.message_id:
                add_log_event(state.message_id, "TELEGRAM_PUBLISHED",
                              f"پست تلگرامی #{post.id} به کانال {channel_id} ارسال گردید.")

            return {"is_sent_to_telegram": True}
        else:
            logger.error(f"ارسال فیزیکی پست تلگرام #{post.id} ناموفق بود.")
            if state.message_id:
                add_log_event(state.message_id, "TELEGRAM_PUBLISH_FAILED",
                              f"خطا در زمان ارسال پست #{post.id} به تلگرام.")

    except PostsContainer.DoesNotExist:
        logger.error(f"PostsContainer with ID {state.post_id} not found in telegram_publisher_node.")
    except Exception as e:
        logger.error(f"Error publishing telegram post {state.post_id}: {e}", exc_info=True)

    return {"is_sent_to_telegram": False}


# ────────────────────────────────────────────────────────────────
# ساخت و کامپایل گراف انتشار (Graph Compilation)
# ────────────────────────────────────────────────────────────────

def get_publisher_workflow_graph():
    """
    ساخت و کامپایل گراف انتشار مقالات وب‌سایت و ارسال پست‌های تلگرام
    """
    workflow = StateGraph(PublisherWorkflowState)

    workflow.add_node("article_publisher", article_publisher_node)
    workflow.add_node("telegram_publisher", telegram_publisher_node)

    workflow.add_edge(START, "article_publisher")
    workflow.add_edge("article_publisher", "telegram_publisher")
    workflow.add_edge("telegram_publisher", END)

    return workflow.compile()
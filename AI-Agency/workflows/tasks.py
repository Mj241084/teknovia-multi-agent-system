import logging
from celery import shared_task
from workflows.models import ReceivedMessages, WorkflowLog
from workflows.graph_workflow import get_graph_app
from workflows.writer_workflow import get_writer_graph
from workflows.image_workflow import get_image_workflow_graph
from workflows.logging_services import initialize_log, add_log_event, finalize_log

logger = logging.getLogger(__name__)


@shared_task(name="workflows.tasks.process_received_message")
def process_received_message(message_id: int):
    """
    تسک سلری جهت اجرای گراف لنگ‌چین اول (پردازش، تشخیص فنی بودن و بررسی تکراری بودن)
    """
    # ۱. تعریف و راه‌اندازی دیتابیسی لاگ مانیتورینگ برای پیام جدید
    initialize_log(message_id)
    add_log_event(message_id, "SYSTEM_START", "پیام تلگرامی جدید دریافت شد و در صف تسک اول سلری قرار گرفت.")

    try:
        msg = ReceivedMessages.objects.get(id=message_id)

        initial_state = {
            "raw_text": msg.raw_text,
            "message_id": msg.id,
            "is_tech": msg.is_tech,
            "is_exists": msg.is_exists
        }

        logger.info(f"Starting LangGraph workflow for Message ID: {message_id}")
        add_log_event(message_id, "LANGGRAPH_PRIMARY", "آغاز اجرای زنجیره اول (تشخیص محتوا و تکراری بودن)...")

        # اجرای گراف اول
        app = get_graph_app()
        app.invoke(initial_state)

        logger.info(f"LangGraph workflow successfully finished for Message ID: {message_id}")
        add_log_event(message_id, "LANGGRAPH_PRIMARY_COMPLETED", "اجرای زنجیره اول با موفقیت خاتمه یافت.")

        # رفرش کردن پیام جهت واکشی مقادیر به‌روز شده توسط گراف اول
        msg.refresh_from_db()

        # زنجیره‌سازی خودکار به فرآیند دوم نگارش
        if msg.is_tech and not msg.is_exists:
            logger.info(f"پیام {message_id} معتبر و غیرتکراری تشخیص داده شد. فرستادن به تسک نگارش مقاله...")
            add_log_event(message_id, "SYSTEM_CHAINING",
                          "پیام واجد شرایط نگارش است؛ ارسال درخواست به صف تسک دوم سلری...")
            process_writing_workflow.delay(msg.id)
        else:
            logger.info(f"پیام {message_id} به دلیل عدم تایید فنی یا تکراری بودن، به بخش نگارش فرستاده نشد.")
            add_log_event(message_id, "SYSTEM_FINISHED_EARLY",
                          "پیام واجد شرایط نگارش نبود (یا تبلیغاتی است یا تکراری). فرآیند متوقف شد.")
            finalize_log(message_id, WorkflowLog.StatusChoices.SKIPPED)

    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages with ID {message_id} does not exist in database.")
        add_log_event(message_id, "CRITICAL_ERROR", "پیام در دیتابیس یافت نشد.")
        finalize_log(message_id, WorkflowLog.StatusChoices.FAILED)
    except Exception as e:
        logger.critical(f"Critical error in executing workflow for Message ID {message_id}: {e}", exc_info=True)
        add_log_event(message_id, "CRITICAL_ERROR", f"بروز خطای غیرمنتظره در اجرای تسک اول: {str(e)}")
        finalize_log(message_id, WorkflowLog.StatusChoices.FAILED)


@shared_task(name="workflows.tasks.process_writing_workflow")
def process_writing_workflow(message_id: int):
    """
    تسک سلری جهت اجرای گراف سردبیری، تحقیق، نگارش و سازماندهی مقالات وب‌سایت و پست تلگرام
    """
    add_log_event(message_id, "SYSTEM_WRITER_START", "تسک دوم (نگارش سردبیری و انتشار) توسط سلری واکشی شد.")

    try:
        msg = ReceivedMessages.objects.get(id=message_id)

        # ساختاربندی رسانه‌های متصل موجود
        medias_info = []
        for m in msg.medias.all():
            medias_info.append({
                "id": m.id,
                "type": m.media_type,
                "description": m.description or "",
                "alt_text": m.alt_text or "تصویر",
                "url": m.media.url if m.media else ""
            })

        initial_state = {
            "received_message_id": msg.id,
            "raw_text": msg.raw_text,
            "links_content": msg.links or "",
            "medias_info": medias_info,
            "research_queries": [],
            "research_results": "",
            "supervisor_decision": "",
            "messages": [],
            "writer_output": None
        }

        logger.info(f"فراخوانی تسک فرآیند نگارش مقاله و پست سردبیری برای پیام: {message_id}")
        add_log_event(message_id, "LANGGRAPH_WRITER", "آغاز اجرای زنجیره سردبیری و تولید متن...")

        # اجرای گراف دوم
        app = get_writer_graph()
        app.invoke(initial_state)

        logger.info(f"اتمام موفقیت‌آمیز فرآیند نگارش پیام با شناسه: {message_id}")

        # فراخوانی خودکار دیسپچر تصاویر پیشنهادی جهت واکشی و ساخت موازی تصاویر جدید
        dispatch_pending_image_suggestions.delay()

    except ReceivedMessages.DoesNotExist:
        logger.error(f"ReceivedMessages با شناسه {message_id} یافت نشد.")
        add_log_event(message_id, "WRITER_CRITICAL_ERROR", "رکورد پیام دریافتی تلگرام برای گام دوم یافت نشد.")
        finalize_log(message_id, WorkflowLog.StatusChoices.FAILED)
    except Exception as e:
        logger.critical(f"خطا در زمان اجرای تسک فرآیند نگارش محتوای پیام {message_id}: {e}", exc_info=True)
        add_log_event(message_id, "WRITER_CRITICAL_ERROR", f"بروز خطای بحرانی در زمان نگارش مقاله: {str(e)}")
        finalize_log(message_id, WorkflowLog.StatusChoices.FAILED)


@shared_task(name="workflows.tasks.process_image_suggestion_task")
def process_image_suggestion_task(tracking_id: str):
    """
    تسک سلری جهت اجرای گراف تخصصی تصویر پیشنهادی بر اساس شناسه یکتای ردیابی.
    مجهز به سد دفاعی بررسی وجود فیزیکی پیام مرجع جهت پیش‌گیری از خطاهای جامعیت کلید خارجی.
    """
    logger.info(f"آغاز پردازش تسک تصویر برای پیشنهاد {tracking_id}...")

    from contents.models import Content, PostsContainer
    sug_data = None

    # بررسی مقاله
    article = Content.objects.filter(suggestions__contains=[{"tracking_id": tracking_id}]).first()
    if article:
        for s in (article.suggestions or []):
            if s.get("tracking_id") == tracking_id:
                sug_data = s
                break

    # بررسی پست شبکه‌های اجتماعی در صورت عدم یافتن در مقاله
    if not sug_data:
        post = PostsContainer.objects.filter(suggestions__contains=[{"tracking_id": tracking_id}]).first()
        if post:
            for s in (post.suggestions or []):
                if s.get("tracking_id") == tracking_id:
                    sug_data = s
                    break

    if not sug_data:
        logger.error(f"پیشنهاد تصویری با شناسه ردیابی {tracking_id} در دیتابیس یافت نشد.")
        return

    # استخراج مقادیر پیشنهادی
    prompt = sug_data.get("prompt", "")
    placements = sug_data.get("placements", [])
    inline_position = sug_data.get("inline_position")
    local_id = sug_data.get("local_id", 1)
    message_id = sug_data.get("message_id", 0)

    # لایه حفاظتی جدید: بررسی وجود فیزیکی پیام خام در دیتابیس جنگو جهت مدیریت تسک‌های مرده
    if message_id and not ReceivedMessages.objects.filter(id=message_id).exists():
        logger.warning(
            f"تسک تصویر {tracking_id} اسکیپ شد. "
            f"پیام مرجع با شناسه {message_id} در پایگاه‌داده وجود ندارد (احتمالاً دیتابیس ریست شده است)."
        )
        return

    try:
        initial_state = {
            "tracking_id": tracking_id,
            "prompt": prompt,
            "placements": placements,
            "inline_position": inline_position,
            "local_id": local_id,
            "message_id": message_id
        }

        # نمونه‌سازی و فراخوانی گراف پردازش تصویر
        app = get_image_workflow_graph()
        app.invoke(initial_state)

        logger.info(f"ورک‌فلوی تصویر با شناسه ردیابی {tracking_id} با موفقیت خاتمه یافت.")

    except Exception as e:
        logger.error(f"خطای بحرانی در فرآیند اجرای تسک تصویر {tracking_id}: {e}", exc_info=True)
        if message_id and ReceivedMessages.objects.filter(id=message_id).exists():
            add_log_event(message_id, "IMAGE_TASK_ERROR", f"بروز خطای غیرمنتظره در تسک پردازش تصویر {local_id}: {str(e)}")


@shared_task(name="workflows.tasks.dispatch_pending_image_suggestions")
def dispatch_pending_image_suggestions():
    """
    دیسپچر هوشمند: واکشی رکوردهای منتظر تصویر، یکپارچه‌سازی بر اساس شناسه ردیابی و شروع موازی تسک‌ها
    """
    from contents.models import Content, PostsContainer

    pending_tracking_ids = set()

    # ۱. واکشی مقالات در انتظار تصاویر تکمیلی
    waiting_contents = Content.objects.filter(suggestions_status=Content.Suggestions.WAITING)
    for article in waiting_contents:
        for sug in (article.suggestions or []):
            if sug.get("status") != "completed":
                pending_tracking_ids.add(sug.get("tracking_id"))

    # ۲. واکشی پست‌های در انتظار تصاویر تکمیلی
    waiting_posts = PostsContainer.objects.filter(suggestions_status=PostsContainer.Suggestions.WAITING)
    for post in waiting_posts:
        for sug in (post.suggestions or []):
            if sug.get("status") != "completed":
                pending_tracking_ids.add(sug.get("tracking_id"))

    if not pending_tracking_ids:
        logger.info("هیچ پیشنهاد تصویری معلقی در وضعیت انتظار یافت نشد.")
        return

    logger.info(f"یافتن تعداد {len(pending_tracking_ids)} پیشنهاد تصویری معلق؛ صف‌بندی تسک‌ها برای هر کدام...")

    # اجرای مجزا و موازی برای هر یک از شناسه‌ها جهت استفاده کامل از پتانسیل سلری
    for tid in pending_tracking_ids:
        process_image_suggestion_task.delay(tid)


@shared_task(name="workflows.tasks.process_seo_workflow")
def process_seo_workflow(content_id: int):
    """
    تسک سلری جهت بهینه‌سازی سئو، دسته‌بندی و برچسب‌گذاری هوشمند مقاله در پس‌زمینه
    """
    logger.info(f"آغاز پردازش تسک سئو برای مقاله {content_id}...")
    from contents.models import Content
    from workflows.seo_workflow import get_seo_workflow_graph

    try:
        article = Content.objects.get(id=content_id)
        # استخراج شناسه پیام مرجع برای درج لاگ‌های پیوسته
        message_id = article.data_source.id if article.data_source else 0

        if message_id:
            add_log_event(message_id, "SEO_START", "آغاز خودکار تسک سوم (بهینه‌سازی سئو و تگ‌گذاری)...")

        initial_state = {
            "content_id": article.id,
            "message_id": message_id,
            "title": article.title,
            "summary": article.summary,
            "content_text": article.content,
            "selected_category_ids": [],
            "selected_tags": [],
            "meta_title": "",
            "meta_description": "",
            "slug": ""
        }

        # نمونه‌سازی و اجرای گراف سئو
        app = get_seo_workflow_graph()
        app.invoke(initial_state)

        logger.info(f"بهینه‌سازی سئو برای مقاله {content_id} با موفقیت به پایان رسید.")

    except Content.DoesNotExist:
        logger.error(f"مقاله‌ای با شناسه {content_id} در دیتابیس یافت نشد.")
    except Exception as e:
        logger.critical(f"خطای غیرمنتظره در زمان اجرای تسک سئو: {e}", exc_info=True)


@shared_task(name="workflows.tasks.process_publisher_workflow")
def process_publisher_workflow(post_id: int):
    """
    تسک متمرکز سلری جهت انتشار مقاله در وب‌سایت و ارسال فیزیکی پست به کانال تلگرام
    """
    logger.info(f"آغاز پردازش تسک متمرکز انتشار برای پست تلگرام {post_id}...")
    from contents.models import PostsContainer
    from workflows.publisher_workflow import get_publisher_workflow_graph

    try:
        post = PostsContainer.objects.get(id=post_id)
        message_id = post.data_source.id if post.data_source else 0

        if message_id:
            add_log_event(message_id, "PUBLISHER_START", "آغاز خودکار تسک انتشار متمرکز (انتشار مقاله و ارسال به تلگرام)...")

        initial_state = {
            "post_id": post.id,
            "message_id": message_id,
            "article_id": post.main_article.id if post.main_article else None,
            "is_published": False,
            "is_sent_to_telegram": False
        }

        # نمونه‌سازی و اجرای گراف انتشار
        app = get_publisher_workflow_graph()
        app.invoke(initial_state)

        logger.info(f"فرآیند انتشار برای پست {post_id} با موفقیت خاتمه یافت.")

    except PostsContainer.DoesNotExist:
        logger.error(f"پست شبکه‌های اجتماعی با شناسه {post_id} در دیتابیس یافت نشد.")
    except Exception as e:
        logger.critical(f"خطای غیرمنتظره در فرآیند اجرا تسک متمرکز انتشار: {e}", exc_info=True)
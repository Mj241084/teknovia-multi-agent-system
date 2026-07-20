import logging
from typing import Any, Dict, List, Optional
from django.db import transaction
from django.utils import timezone
from workflows.models import WorkflowLog

logger = logging.getLogger(__name__)


@transaction.atomic
def initialize_log(message_id: int) -> WorkflowLog:
    """
    ایجاد یا بازیابی لاگ فرآیند به صورت تراکنشی جهت جلوگیری از همپوشانی
    """
    log_obj, created = WorkflowLog.objects.select_for_update().get_or_create(message_id=message_id)
    if created:
        log_obj.timeline_events = []
        log_obj.metadata = {}
        log_obj.status = WorkflowLog.StatusChoices.RUNNING
        log_obj.save()
    return log_obj


@transaction.atomic
def add_log_event(message_id: int, step_name: str, message: str, details: Optional[Dict[str, Any]] = None):
    """
    افزودن یک واقعه متنی خوانا به تایم‌لاین پیام همراه با ثبت خودکار زمان وقوع
    """
    try:
        log_obj, _ = WorkflowLog.objects.select_for_update().get_or_create(message_id=message_id)
        events = list(log_obj.timeline_events or [])
        events.append({
            "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
            "step": step_name,
            "message": message,
            "details": details if details else {}
        })
        log_obj.timeline_events = events
        log_obj.save()
    except Exception as e:
        logger.error(f"Error adding log event for message {message_id}: {e}")


@transaction.atomic
def update_log_metadata(message_id: int, key: str, value: Any):
    """
    به‌روزرسانی متادیتا و ذخیره ساختاریافته پاسخ‌های هوش مصنوعی
    """
    try:
        log_obj, _ = WorkflowLog.objects.select_for_update().get_or_create(message_id=message_id)
        meta = dict(log_obj.metadata or {})
        meta[key] = value
        log_obj.metadata = meta
        log_obj.save()
    except Exception as e:
        logger.error(f"Error updating metadata for message {message_id}: {e}")


@transaction.atomic
def finalize_log(message_id: int, status: str):
    """
    نهایی‌سازی وضعیت فرآیند اجرای پیام در دیتابیس
    """
    try:
        log_obj, _ = WorkflowLog.objects.select_for_update().get_or_create(message_id=message_id)
        log_obj.status = status
        log_obj.save()
    except Exception as e:
        logger.error(f"Error finalizing WorkflowLog status for message {message_id}: {e}")
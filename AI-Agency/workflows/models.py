import numpy as np
import logging
from django.db import models
from contents.models import MediaContainer, EmbeddingError

logger = logging.getLogger(__name__)


class ReceivedMessages(models.Model):
    class Steps(models.IntegerChoices):
        OBSERVING = 1, 'tech_check'
        CHECKING = 2, 'exists_check'
        FETCHING = 3, 'fetching_links'
        ANALYZING = 4, 'analyzing_medias'
        SAVING = 5, 'saving_medias'
        FINISHED = 6, 'finished'

    raw_text = models.TextField()
    telegram_group_id = models.BigIntegerField(
        'شناسه آلبوم تلگرام',
        null=True,
        blank=True,
        db_index=True
    )
    links = models.TextField(null=True, blank=True)
    medias = models.ManyToManyField(MediaContainer)
    is_tech = models.BooleanField(default=False)
    is_exists = models.BooleanField(default=False)
    is_finished = models.BooleanField(default=False)
    step = models.PositiveSmallIntegerField(
        choices=Steps.choices,
        default=Steps.OBSERVING
    )
    external_id = models.PositiveIntegerField(
        'شناسه اختصاصی بردار (TurboVec)',
        unique=True, db_index=True, null=True, blank=True
    )
    embedding_data = models.BinaryField('امبدینگ کل سند', null=True, blank=True)

    def next_step(self):
        if self.step < self.Steps.SAVING:
            self.step += 1
            self.save()
        return self.step

    def prev_step(self):
        if self.step > self.Steps.OBSERVING:
            self.step -= 1
            self.save()
        return self.step

    def set_step(self, step):
        self.step = step
        self.save()
        return self.step

    def get_step_name(self):
        return self.Steps(self.step).label

    def set_embedding(self, embedding_list):
        try:
            if not isinstance(embedding_list, (list, tuple, np.ndarray)):
                raise TypeError("embedding_list باید لیست یا ndarray باشد")
            arr = np.array(embedding_list, dtype=np.float32)
            self.embedding_data = arr.tobytes()
        except Exception as e:
            logger.error(f"ReceivedMessages ID={self.pk}: خطا در ذخیره امبدینگ -> {e}")
            raise EmbeddingError("خطا در ذخیره امبدینگ")

    def get_embedding(self):
        if self.embedding_data is None:
            return None
        return np.frombuffer(self.embedding_data, dtype=np.float32)


class WorkflowLog(models.Model):
    class StatusChoices(models.TextChoices):
        RUNNING = 'RUNNING', 'در حال اجرا'
        COMPLETED = 'COMPLETED', 'موفقیت‌آمیز'
        FAILED = 'FAILED', 'خطا در اجرا'
        SKIPPED = 'SKIPPED', 'رد شده (اسکیپ)'

    message = models.OneToOneField(
        ReceivedMessages,
        on_delete=models.CASCADE,
        related_name='workflow_log',
        verbose_name='پیام تلگرامی مرتبط'
    )
    created_at = models.DateTimeField('شروع فرآیند', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین به‌روزرسانی', auto_now=True)

    # رویدادهای تایم‌لاین به صورت آرایه‌ای از دیکشنری‌ها
    timeline_events = models.JSONField('رویدادهای تایم‌لاین', default=list, blank=True)

    # متادیتا و جزییات عمیق پاسخ‌های هوش مصنوعی
    metadata = models.JSONField('متادیتا و جزئیات فنی', default=dict, blank=True)

    status = models.CharField(
        'وضعیت کل فرآیند',
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.RUNNING
    )

    class Meta:
        verbose_name = 'لاگ اجرای ورک‌فلو'
        verbose_name_plural = 'لاگ‌های اجرای ورک‌فلو'
        ordering = ['-created_at']

    def __str__(self):
        return f"لاگ اجرای پیام {self.message_id} - {self.get_status_display()}"
import logging
import secrets
import string
import io
import numpy as np
from django.db import models, DatabaseError
from django.db.models import ManyToManyField
from django.urls import reverse
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.conf import settings
from PIL import Image

# ────────────────────────────────────────────────────────────────
# Logger Setup
# ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Custom Exceptions
# ────────────────────────────────────────────────────────────────
class ShortCodeGenerationError(Exception):
    """خطا در تولید کد کوتاه یکتا"""
    pass


class EmbeddingError(Exception):
    """خطا در عملیات امبدینگ"""
    pass


class MediaProcessingError(Exception):
    """خطا در پردازش رسانه"""
    pass


# ────────────────────────────────────────────────────────────────
# Custom Tag Model (سفارشی و مستقل بومی بدون وابستگی به taggit)
# ────────────────────────────────────────────────────────────────
class Tag(models.Model):
    name = models.CharField('نام', max_length=100, unique=True)
    slug = models.SlugField('اسلاگ',allow_unicode=True, max_length=100, unique=True, blank=True)
    views_count = models.PositiveIntegerField('تعداد بازدید', default=0)
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)

    class Meta:
        verbose_name = 'برچسب'
        verbose_name_plural = 'برچسب‌ها'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ────────────────────────────────────────────────────────────────
# Category Model
# ────────────────────────────────────────────────────────────────
class Category(models.Model):
    name = models.CharField('نام', max_length=100, unique=True)
    slug = models.SlugField('اسلاگ', max_length=100,allow_unicode=True, unique=True, blank=True)
    description = models.TextField('توضیحات', blank=True)
    meta_title = models.CharField('عنوان متا', max_length=70, blank=True)
    meta_description = models.CharField('توضیحات متا', max_length=160, blank=True)

    # فیلد آیکون بومی آپلود شونده در آروان کلود (با پشتیبانی از فرمت‌های SVG و تصویری معمولی)
    icon = models.FileField(
        'آیکون دسته‌بندی (SVG یا تصویر)',
        upload_to='categories/icons/',
        blank=True,
        null=True
    )

    # فیلد لوگوی فیزیکی بزرگ بومی
    logo = models.ImageField(
        'لوگو دسته‌بندی',
        upload_to='categories/logos/',
        blank=True,
        null=True
    )

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='دسته والد'
    )
    is_active = models.BooleanField('فعال', default=True)
    order = models.PositiveIntegerField('ترتیب', default=0)
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    indexable = models.BooleanField('قابل ایندکس', default=True)
    views_count = models.PositiveIntegerField('تعداد بازدید', default=0)

    class Meta:
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'
        ordering = ['order', 'name']

    def clean(self):
        """اعتبارسنجی مدل قبل از ذخیره"""
        if self.parent == self:
            logger.warning(f"Category {self.name}: نمی‌تواند والد خود باشد")
            raise ValidationError('دسته‌بندی نمی‌تواند والد خود باشد.')

    def save(self, *args, **kwargs):
        try:
            if not self.slug:
                self.slug = slugify(self.name, allow_unicode=True)
                logger.debug(f"Category '{self.name}': اسلاگ خودکار تولید شد -> '{self.slug}'")
            if not self.meta_title:
                self.meta_title = self.name

            self.clean()

            # ۱. بهینه‌سازی فیزیکی آیکون آپلود شده
            if self.icon and hasattr(self.icon, 'file'):
                try:
                    # اگر فرمت فایل وکتور متنی (SVG) نباشد، آن را به عنوان تصویر معمولی فشرده می‌کنیم
                    if not self.icon.name.lower().endswith('.svg'):
                        img = Image.open(self.icon)
                        if img.format != 'WEBP' or self.icon.size > 50 * 1024:
                            out_io = io.BytesIO()
                            if img.mode in ("RGBA", "LA"):
                                img = img.convert("RGBA")
                            else:
                                img = img.convert("RGB")

                            # مقیاس بسیار کوچک و سبک برای ابعاد آیکون
                            img.thumbnail((150, 150), Image.Resampling.LANCZOS)
                            img.save(out_io, format="WEBP", quality=80)

                            icon_filename = f"{self.slug or 'category_icon'}_icon.webp"
                            self.icon.save(icon_filename, ContentFile(out_io.getvalue()), save=False)
                except Exception as icon_err:
                    logger.warning(f"Error converting category icon to WebP: {icon_err}")

            # ۲. بهینه‌سازی فیزیکی لوگو به فرمت کم حجم webp
            if self.logo and hasattr(self.logo, 'file'):
                try:
                    img = Image.open(self.logo)
                    if img.format != 'WEBP' or self.logo.size > 120 * 1024:
                        out_io = io.BytesIO()
                        if img.mode in ("RGBA", "LA"):
                            img = img.convert("RGBA")
                        else:
                            img = img.convert("RGB")

                        # لوگوی دسته‌بندی با مقیاس مناسب
                        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                        img.save(out_io, format="WEBP", quality=80)

                        logo_filename = f"{self.slug or 'category_logo'}.webp"
                        self.logo.save(logo_filename, ContentFile(out_io.getvalue()), save=False)
                except Exception as logo_err:
                    logger.warning(f"Error converting category logo to WebP: {logo_err}")

            super().save(*args, **kwargs)
            logger.info(f"Category '{self.name}' با موفقیت ذخیره شد. ID={self.pk}")

        except DatabaseError as e:
            logger.error(f"Category '{self.name}': خطای دیتابیس -> {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Category '{self.name}': خطای غیرمنتظره -> {e}", exc_info=True)
            raise

    def __str__(self):
        return self.name


# ────────────────────────────────────────────────────────────────
# MediaContainer Model
# ────────────────────────────────────────────────────────────────
class MediaContainer(models.Model):
    class MediaTypes(models.TextChoices):
        IMAGE = 'image', 'تصویر'
        VIDEO = 'video', 'ویدیو'

    media_type = models.CharField(choices=MediaTypes, max_length=20)
    media = models.FileField(
        upload_to='news/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='رسانه'
    )
    is_used = models.BooleanField(default=False)
    is_analyzed = models.BooleanField(default=False)
    source_url = models.URLField(max_length=500, null=True, blank=True)
    description = models.TextField(blank=True)
    alt_text = models.CharField(max_length=100, blank=True)
    original_width = models.PositiveIntegerField(null=True, blank=True)
    original_height = models.PositiveIntegerField(null=True, blank=True)
    original_size_kb = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'رسانه'
        verbose_name_plural = 'رسانه‌ها'

    def clean(self):
        """اعتبارسنجی فایل و ابعاد"""
        try:
            img = Image.open(self.media)
            self.original_width, self.original_height = img.size
            logger.debug(f"MediaContainer ID={self.pk}: ابعاد تصویر {img.size}")
        except Exception as e:
            logger.warning(f"MediaContainer: عدم توانایی در خواندن ابعاد تصویر -> {e}")

    def save(self, *args, **kwargs):
        try:
            if ((self.original_width is None or self.original_height is None) and self.media
                    and self.media_type == self.MediaTypes.IMAGE):
                self.clean()
            super().save(*args, **kwargs)
            logger.info(f"MediaContainer با موفقیت ذخیره شد. ID={self.pk}, Type={self.media_type}")
        except DatabaseError as e:
            logger.error(f"MediaContainer: خطای دیتابیس -> {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"MediaContainer: خطای غیرمنتظره -> {e}", exc_info=True)
            raise

    def __str__(self):
        return f"{self.media_type} - {self.pk}"


# ────────────────────────────────────────────────────────────────
# Content Model
# ────────────────────────────────────────────────────────────────
class Content(models.Model):
    class StatusChoices(models.TextChoices):
        DRAFT = 'draft', 'پیش‌نویس'
        PUBLISHED = 'published', 'منتشر شده'
        ARCHIVED = 'archived', 'بایگانی'

    class ImportanceChoices(models.IntegerChoices):
        NORMAL = 1, 'عادی'
        URGENT = 2, 'فوری'
        FEATURED = 3, 'ویژه'

    class ContentTypeChoices(models.TextChoices):
        NEWS = 'News', 'خبر'
        ARTICLE = 'Article', 'مقاله'

    class Suggestions(models.TextChoices):
        EMPTY = 'no suggestions', 'بدون پیشنهاد'
        WAITING = 'waiting for generating images', 'منتظر ساخت عکس'
        PROCESSING = 'processing generated images', 'آنالیز عکس ها و ذخیره سازی'
        FAILED = 'failed', 'فرآیند با خطا مواجه شد'
        FINISHED = 'finished generating images', 'اتمام ساخته شدن'

    title = models.CharField('عنوان', max_length=200)
    slug = models.SlugField('اسلاگ', max_length=200,allow_unicode=True, unique=True, blank=True)
    summary = models.TextField('خلاصه', max_length=500)
    content = models.TextField('محتوا (مارک‌داون)')
    short_code = models.CharField(
        'کد کوتاه اشتراک گذاری',
        max_length=10,
        unique=True,
        blank=True,
        db_index=True
    )

    schema_type = models.CharField(
        'نوع Schema',
        max_length=50,
        default=ContentTypeChoices.NEWS,
        choices=ContentTypeChoices,
        blank=True
    )

    meta_title = models.CharField('عنوان متا', max_length=70, blank=True)
    meta_description = models.CharField('توضیحات متا', max_length=160, blank=True)
    canonical_url = models.URLField('URL کانونیکال', blank=True)

    featured_media = models.ForeignKey(
        MediaContainer, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='featured_contents',
        verbose_name='رسانه اصلی',
    )
    media_thumbnail = models.ImageField(
        upload_to='news/%Y/%m/thumbnails/',
        blank=True,
        null=True,
        verbose_name='تامبنیل رسانه'
    )
    media_image_small = models.ImageField(
        upload_to='news/%Y/%m/smalls/',
        blank=True,
        null=True,
        verbose_name='عکس کوچک'
    )

    author = models.CharField(
        verbose_name='نویسنده',
        max_length=70,
        default=settings.SITE_NAME
    )
    category = models.ManyToManyField(
        Category,
        verbose_name='دسته‌بندی'
    )

    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name='contents',
        verbose_name='برچسب‌ها'
    )

    indexable = models.BooleanField('قابل ایندکس', default=True)

    data_source = models.ForeignKey(
        'workflows.ReceivedMessages',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contents',
        verbose_name='منبع پیام دریافتی'
    )

    status = models.CharField(
        'وضعیت',
        max_length=10,
        choices=StatusChoices,
        default=StatusChoices.DRAFT
    )
    importance = models.IntegerField(
        'اهمیت',
        choices=ImportanceChoices,
        default=ImportanceChoices.NORMAL
    )

    publish_date = models.DateTimeField('تاریخ انتشار', null=True, blank=True)
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('تاریخ بروزرسانی', auto_now=True)

    suggestions_status = models.CharField(default=Suggestions.EMPTY, max_length=30, choices=Suggestions.choices,
                                          blank=True)
    suggestions = models.JSONField(null=True, blank=True)

    views_count = models.PositiveIntegerField('تعداد بازدید', default=0)
    likes_count = models.PositiveIntegerField('تعداد لایک', default=0)
    reading_time = models.PositiveIntegerField('زمان مطالعه', default=0)
    share_count = models.PositiveIntegerField('تعداد اشتراک‌گذاری', default=0)

    external_id = models.PositiveIntegerField(
        'شناسه اختصاصی بردار (TurboVec)',
        unique=True, db_index=True, null=True, blank=True
    )
    embedding_data = models.BinaryField('امبدینگ کل سند', null=True, blank=True)

    class Meta:
        verbose_name = 'محتوا'
        verbose_name_plural = 'محتواها'
        ordering = ['-publish_date', '-created_at']

    def _generate_short_code(self):
        try:
            return ''.join(
                secrets.choice(string.ascii_letters + string.digits)
                for _ in range(6)
            )
        except Exception as e:
            logger.error(f"Content '{self.title}': خطا در تولید کد کوتاه -> {e}", exc_info=True)
            raise ShortCodeGenerationError("خطا در تولید کد کوتاه") from e

    def _ensure_unique_short_code(self):
        max_attempts = 15
        for attempt in range(1, max_attempts + 1):
            try:
                code = self._generate_short_code()
                if not Content.objects.filter(short_code=code).exists():
                    self.short_code = code
                    logger.debug(f"Content '{self.title}': کد کوتاه تولید شد -> '{code}' (تلاش {attempt})")
                    return
            except DatabaseError as e:
                logger.error(f"Content '{self.title}': خطای دیتابیس در بررسی کد -> {e}")
                raise
            except Exception as e:
                logger.warning(f"Content '{self.title}': تلاش {attempt} ناموفق -> {e}")

        logger.critical(f"Content '{self.title}': عدم موفقیت در تولید کد کوتاه پس از {max_attempts} تلاش")
        raise ShortCodeGenerationError(
            f"امکان تولید کد کوتاه یکتا پس از {max_attempts} تلاش وجود ندارد."
        )

    def _calculate_reading_time(self):
        try:
            if self.content and not self.reading_time:
                word_count = len(self.content.split())
                self.reading_time = max(1, round(word_count / 200))
                logger.debug(f"Content '{self.title}': زمان مطالعه = {self.reading_time} دقیقه ({word_count} کلمه)")
        except Exception as e:
            logger.warning(f"Content '{self.title}': خطا در محاسبه زمان مطالعه -> {e}")
            self.reading_time = 1

    def clean(self):
        errors = {}
        if not self.title or len(self.title.strip()) < 3:
            errors['title'] = 'عنوان باید حداقل ۳ کاراکتر باشد.'
        if not self.content or len(self.content.strip()) < 20:
            errors['content'] = 'محتوا باید حداقل ۲۰ کاراکتر باشد.'
        if errors:
            logger.warning(f"Content: اعتبارسنجی ناموفق -> {errors}")
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        try:
            if not self.slug:
                self.slug = slugify(self.title, allow_unicode=True)
                logger.debug(f"Content '{self.title}': اسلاگ فارسی تولید شد -> '{self.slug}'")

            if not self.short_code:
                self._ensure_unique_short_code()

            self._calculate_reading_time()
            self.clean()
            super().save(*args, **kwargs)
            logger.info(f"Content '{self.title}' با موفقیت ذخیره شد. ID={self.pk}, Slug={self.slug}")

        except ShortCodeGenerationError as e:
            logger.critical(f"Content '{self.title}': {e}", exc_info=True)
            raise
        except DatabaseError as e:
            logger.error(f"Content '{self.title}': خطای دیتابیس -> {e}", exc_info=True)
            raise
        except ValidationError as e:
            logger.warning(f"Content '{self.title}': خطای اعتبارسنجی -> {e}")
            raise
        except Exception as e:
            logger.error(f"Content '{self.title}': خطای غیرمنتظره -> {e}", exc_info=True)
            raise

    def get_reading_time_display(self):
        try:
            if self.reading_time <= 1:
                return "۱ دقیقه مطالعه"
            return f"{self.reading_time} دقیقه مطالعه"
        except Exception as e:
            logger.warning(f"Content '{self.title}': خطا در نمایش زمان مطالعه -> {e}")
            return "زمان نامشخص"

    def get_absolute_url(self):
        try:
            return reverse('content:detail', kwargs={'slug': self.slug})
        except Exception as e:
            logger.error(f"Content '{self.title}': خطا در ساخت URL -> {e}", exc_info=True)
            return '#'

    def set_embedding(self, embedding_list):
        try:
            if not isinstance(embedding_list, (list, tuple, np.ndarray)):
                raise TypeError(f"embedding_list باید لیست یا ndarray باشد، دریافت شد: {type(embedding_list)}")

            if len(embedding_list) == 0:
                raise ValueError("embedding_list نمی‌تواند خالی باشد")

            arr = np.array(embedding_list, dtype=np.float32)
            self.embedding_data = arr.tobytes()
            logger.info(f"Content '{self.title}': امبدینگ با ابعاد {arr.shape} ذخیره شد")

        except (TypeError, ValueError) as e:
            logger.error(f"Content '{self.title}': خطای اعتبارسنجی امبدینگ -> {e}", exc_info=True)
            raise EmbeddingError(f"خطا در ذخیره امبدینگ: {e}") from e
        except Exception as e:
            logger.error(f"Content '{self.title}': font_error در ذخیره امبدینگ -> {e}", exc_info=True)
            raise EmbeddingError("خطای غیرمنتظره در ذخیره امبدینگ") from e

    def get_embedding(self):
        try:
            if self.embedding_data is None:
                return None
            arr = np.frombuffer(self.embedding_data, dtype=np.float32)
            return arr
        except Exception as e:
            logger.error(f"Content '{self.title}': خطا در بازیابی امبدینگ -> {e}", exc_info=True)
            raise EmbeddingError("خطا در بازیابی امبدینگ") from e

    def clear_embedding(self):
        try:
            self.embedding_data = None
            self.save(update_fields=['embedding_data'])
            logger.info(f"Content '{self.title}': امبدینگ پاک شد")
        except Exception as e:
            logger.error(f"Content '{self.title}': خطا در پاک کردن امبدینگ -> {e}", exc_info=True)
            raise

    def __str__(self):
        return self.title


class PostsContainer(models.Model):
    class State(models.TextChoices):
        DRAFT = 'DRAFT', 'پیش نویس'
        SENT = 'SENT', 'ارسال شده'

    class Suggestions(models.TextChoices):
        EMPTY = 'no suggestions', 'بدون پیشنهاد'
        WAITING = 'waiting for generating images', 'منتظر ساخت عکس'
        PROCESSING = 'processing generated images', 'آنالیز عکس ها و ذخیره سازی'
        FAILED = 'failed', 'فرآیند با خطا مواجه شد'
        FINISHED = 'finished generating images', 'اتمام ساخته شدن'

    content = models.TextField()
    main_article = models.ForeignKey(Content, on_delete=models.SET_NULL, null=True, blank=True)
    state = models.CharField(choices=State.choices, max_length=10, default=State.DRAFT)
    medias = ManyToManyField(MediaContainer)
    suggestions_status = models.CharField(default=Suggestions.EMPTY, max_length=30, choices=Suggestions.choices,
                                          blank=True)
    suggestions = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    data_source = models.ForeignKey(
        'workflows.ReceivedMessages',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts',
        verbose_name='منبع پیام دریافتی'
    )
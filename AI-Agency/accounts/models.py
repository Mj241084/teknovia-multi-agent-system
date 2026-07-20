from django.db import models
from django.db.models import F

class ApiContainer(models.Model):
    class Providers(models.TextChoices):
        GOOGLE="gemini","جمنای"
        GROQ="groq","گراک"
        JINA="jina","جینا"
        DEEPSEEK="deepseek","دیپ سیک"
        OPENROUTER="openrouter","اوپن روتر"
        DEAPI="deapi","Deapi"
        TAVILY="tavily","Tavily"
        SERPER="serper","Serper"

    key=models.CharField(max_length=200)
    provider = models.CharField(choices=Providers.choices,max_length=30)
    today_use=models.IntegerField(default=0)
    total_use=models.IntegerField(default=0)
    created=models.DateTimeField(auto_now_add=True)
    updated=models.DateTimeField(auto_now=True)
    status=models.BooleanField(default=True)

    def increment_usage(self, amount=1):
        """
        افزایش میزان استفاده امروز و کل به صورت ایمن و همزمان
        """
        self.today_use = F('today_use') + amount
        self.total_use = F('total_use') + amount
        # برای افزایش سرعت و کارایی، فقط همین دو فیلد ذخیره می‌شوند
        self.save(update_fields=['today_use', 'total_use'])

        # مقدار فیلدها را در حافظه پایتون به روز می‌کنیم تا بلافاصله قابل استفاده و نمایش باشند
        self.refresh_from_db(fields=['today_use', 'total_use'])


class Comment(models.Model):
    """مدل دیدگاه‌های مقالات با سیستم تایید و ساختار بازگشتی"""
    class CommentStatus(models.TextChoices):
        UNDER_REVIEW = 'UNDER_REVIEW', 'در حال بررسی'
        APPROVED = 'APPROVED', 'تایید شده'
        REJECTED = 'REJECTED', 'رد شده'

    content = models.ForeignKey(
        'contents.Content',
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='محتوا'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name='پاسخ به'
    )
    name = models.CharField('نام فرستنده', max_length=100)
    email = models.EmailField('ایمیل فرستنده', blank=True, null=True)
    text = models.TextField('متن نظر')
    status = models.CharField(
        'وضعیت انتشار',
        max_length=20,
        choices=CommentStatus.choices,
        default=CommentStatus.UNDER_REVIEW
    )
    created_at = models.DateTimeField('تاریخ ثبت', auto_now_add=True)
    likes_count = models.PositiveIntegerField('تعداد لایک کامنت', default=0)

    class Meta:
        verbose_name = 'دیدگاه'
        verbose_name_plural = 'دیدگاه‌ها'
        ordering = ['created_at']

    def __str__(self):
        return f"نظر {self.name} برای {self.content_id}"
from typing import List, Optional
from pydantic import BaseModel, Field

class GlobalSuggestion(BaseModel):
    id: int = Field(
        ...,
        description="یک شناسه عددی یکتای محلی ترتیبی (مثلاً 1، 2) برای ارجاع سیستم به این پیشنهاد تولید تصویر جدید."
    )
    prompt_or_description: str = Field(
        ...,
        description=(
            "توضیحات غنی بصری برای پیدا کردن عکس مناسب از اینترنت یا پرامپت پیشنهادی برای ساخت تصویر توسط هوش مصنوعی. "
            "اگر تصویر باید یک عکس واقعی از دنیای واقعی، اشخاص، شرکت‌ها، لوگوها یا محصولات سخت‌افزاری واقعی فیزیکی باشد "
            "(مانند دفتر مرکزی انویدیا، تراشه Apple M4، لوگوی گوگل یا یک رویداد خبری خاص)، "
            "توضیحات را کاملاً واقعی و منطبق بر جستجوی وب بنویسید. "
            "اما اگر تصویر یک مفهوم انتزاعی، گرافیکی، هنری یا غیرواقعی است، یک پرامپت باکیفیت انگلیسی برای تولید آن توسط Midjourney/Flux بنویسید."
        )
    )
    placements: List[str] = Field(
        ...,
        description="محل‌های قرارگیری تصویر در خروجی‌ها. مقادیر مجاز: ['article_featured', 'article_inline', 'telegram_post']"
    )
    inline_position: Optional[str] = Field(
        None,
        description="در صورت قرارگیری به صورت بین‌متنی (article_inline)، محل قرارگیری دقیق آن ذکر شود (مثلا: 'بین پاراگراف ۲ و ۳')."
    )

class ArticleSchema(BaseModel):
    title: str = Field(..., description="عنوان جذاب، خلاقانه و سئو شده برای انتشار در وب‌سایت خبرگزاری به زبان فارسی.")
    summary: str = Field(..., description="خلاصه‌ای رسا و حرفه‌ای (زیر ۵۰۰ کاراکتر) از کل محتوا به زبان فارسی.")
    content: str = Field(
        ...,
        description=(
            "بدنه اصلی متن مقاله به فرمت مارک‌داون (Markdown) به زبان فارسی. "
            "قوانین قرارگذاری رسانه در متن: "
            "۱. برای قرار دادن رسانه‌های موجود ورودی، از ساختار دقیق ![alt_text](media_id:ID) استفاده کنید. (مانند ![رونمایی کارت گرافیک](media_id:12)) "
            "۲. برای قرار دادن تصاویر پیشنهادی جدید، از ساختار دقیق مارک‌داون جایگزین ![alt_text](suggestion_id:LOCAL_ID) استفاده کنید. (مانند ![تراشه جدید گوگل پیکسل](suggestion_id:1))"
        )
    )
    used_images: List[int] = Field(
        default=[],
        description="لیست شناسه‌های عددی (ID) مربوط به رسانه‌های موجود ورودی که در بدنه این مقاله گنجانده شده‌اند."
    )
    importance: int = Field(
        default=1,
        description="درجه اهمیت مقاله: ۱ (عادی)، ۲ (فوری)، ۳ (ویژه)."
    )
    type: str = Field(
        default="News",
        description="نوع محتوا طبق دسته‌بندی سایت: 'News' یا 'Article'."
    )
    featured_media: Optional[int] = Field(
        default=None,
        description="شناسه رسانه موجودی که قرار است تصویر شاخص (Featured) مقاله وب‌سایت باشد."
    )
    indexable: bool = Field(default=True, description="آیا این محتوا توسط موتورهای جستجو ایندکس شود؟")

class TelegramPostSchema(BaseModel):
    content: str = Field(
        ...,
        description="متن پیش‌نویس نهایی جهت انتشار در کانال تلگرام به زبان فارسی. برای اخبار بسیار مهم از هوک‌های جذاب استفاده شود."
    )
    selected_medias: List[int] = Field(
        default=[],
        description="لیست شناسه‌های رسانه‌های موجود ورودی که به عنوان ضمیمه این پست در کانال تلگرام انتخاب شده‌اند."
    )

class WriterOutputSchema(BaseModel):
    skip: bool = Field(
        default=False,
        description="اگر کل داده ورودی فاقد ارزش انتشاراتی یا خبری برای وب‌سایت و کانال تلگرام بود، True قرار داده شود."
    )
    skip_reason: Optional[str] = Field(
        default=None,
        description="علت رد یا نادیده گرفتن خبر ورودی."
    )
    article: Optional[ArticleSchema] = Field(
        default=None,
        description="پیش‌نویس نهایی ساختاریافته وب‌سایت. در صورتی که محتوا ارزش ثبت در وب‌سایت را ندارد اما برای پست شبکه‌های اجتماعی مناسب است، خالی (None) گذاشته شود."
    )
    post: Optional[TelegramPostSchema] = Field(
        default=None,
        description="پیش‌نویس نهایی پست شبکه‌های اجتماعی (تلگرام). در صورتی که خبر اسکیپ نشده باشد، حتماً تکمیل شود."
    )
    global_suggestions: List[GlobalSuggestion] = Field(
        default=[],
        description="لیست کل پیشنهادات برای تولید تصاویر تکمیلی جدید به شکل بهینه و فاقد همپوشانی تکراری."
    )
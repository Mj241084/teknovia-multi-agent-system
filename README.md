# تکنوویا (Teknovia) — معماری خبرگزاری خودکار با ۱۳ ایجنت هوش مصنوعی

خبرگزاری خودکار برای رصد، تحقیق، نگارش، ویرایش، تولید تصویر و انتشار هوشمند اخبار در وب‌سایت و کانال تلگرام.

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Astro](https://img.shields.io/badge/Astro-7.0-BC52EE.svg?logo=astro&logoColor=white)](https://astro.build/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange.svg)](https://www.langchain.com/langgraph)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)

---

## ایده‌ی اصلی پروژه

هدف تکنوویا ساخت سیستمی بود که بدون نیاز به اپراتور انسانی، اخبار فناوری را از کانال‌های خبری دریافت کند، محتوای تکراری و اسپم را کنار بگذارد، موضوع را در وب جستجو و تکمیل کند، متن سئوشده و روان بنویسد، تصویر بسازد و در نهایت روی سایت و کانال تلگرام منتشر کند.

برای اجرای این خط تولید، یک سیستم چندعاملی (Multi-Agent) با ۱۳ ایجنت هوش مصنوعی طراحی کردم که در قالب ۵ ورک‌فلو متوالی روی LangGraph کار می‌کنند.

---

## معماری ورک‌فلوها و چالش‌های فنی

### دریافت اخبار و پردازش آلبوم‌ها (Telethon Listener)

ورودی سیستم، پیام‌های دریافتی از کلاینت Telethon است. تلگرام پست‌های چندرسانه‌ای (آلبوم) را در قالب چند پیام مجزا با یک `grouped_id` یکسان می‌فرستد. اگر سیستم با دریافت اولین پیام شروع به پردازش می‌کرد، مابقی تصاویر آلبوم از دست می‌رفتند. همچنین لینک‌های متنی تلگرام (`[متن](url)`) در دریافت ساده به متن معمولی تبدیل می‌شدند.

برای حل این مشکل، یک مکانیزم Debounce ۲ ثانیه‌ای نوشتم تا سیستم منتظر دریافت تمام پارت‌های آلبوم بماند. سپس با استفاده از `markdown.unparse` در تلتون، انکودینگ UTF-16 پیام‌ها به مارک‌داون تبدیل شد تا پیوندها بدون خراب شدن آفست متنی حفظ شوند.

---

### ورک‌فلو ۱: فیلتر اسپم، تشخیص معنایی اخبار تکراری و دیتابیس برداری

![Processor Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972503/1_processor_workflow_tldqci.png)

1. **فیلتر اسپم:** پیام‌های ورودی ابتدا توسط `deepseek-v4-pro` بررسی می‌شوند تا آگهی‌های تبلیغاتی، فروش VPN و استخدامی حذف شوند.
2. **تشخیص اخبار تکراری با TurboVec و FastAPI:**
   برای تشخیص شباهت مفهومی اخبار از مدل `gemini-embedding-2` (بردار ۷۶۸ بعدی) و دیتابیس برداری TurboVec استفاده کردم. در پیاده‌سازی اولیه، لود کردن مستقیم دیتابیس برداری در جنگو باعث بالا رفتن شدید مصرف RAM به ازای هر ورکر WSGI/ASGI می‌شد و سنکرون نگه‌داشتن ایندکس بین ورکرها چالش‌برانگیز بود.
   
   برای حل این مشکل، دیتابیس برداری را به یک میکرو‌سرویس مجزا روی FastAPI منتقل کردم. از آنجا که TurboVec امکان ذخیره متادیتای پیچیده را ندارد، شناسه جنگو (`django_id`) را در ایندکس TurboVec نگاشت کردم و در دیتابیس PostgreSQL علاوه بر شناسه بردار، **خروجی باینری امبدینگ** را هم ذخیره کردم. این کار باعث شد علاوه بر ارتباط اتمیک دو دیتابیس، در صورت از دست رفتن ایندکس برداری بتوان کل دیتابیس برداری را مستقیماً از روی Postgres بازیابی کرد، بدون آنکه نیازی به فراخوانی مجدد API گوگل باشد.

   **منطق سنجش شباهت:**
   - شباهت زیر ۶۵٪: خبر جدید است.
   - شباهت بالای ۹۲٪: خبر تکراری است و بلافاصله رد می‌شود.
   - بین ۶۵٪ تا ۹۲٪: موضوع به `deepseek-v4-flash` ارجاع داده می‌شود تا تصمیم نهایی را بگیرد.

3. **ویرایش تصویر و حذف واترماک:**
   تصاویر با Gemini Vision تحلیل می‌شوند و در صورت وجود واترماک به `QwenImageEdit_Plus_NF4` روی deAPI ارسال می‌شوند. برای جلوگیری از پاک شدن المان‌های اصلی رابط کاربری (مثل دکمه‌ها یا قیمت‌ها که هوش مصنوعی آن‌ها را با واترماک اشتباه می‌گرفت)، پرامپت سیستم را طوری تنظیم کردم که فقط لوگوها و واترماک‌های ناشر حذف شوند.

---

### ورک‌فلو ۲: تحقیق متوالی و نگارش مقاله

![Writer Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972565/2_writer_workflow_nykfyz.png)

1. **جستجوی زنجیره‌ای (Sequential Adaptive Search):**
   جستجوهای همزمان معمولاً نتایج سطحی می‌دهند و احتمال توهم مدل (Hallucination) را بالا می‌برند. ایجنت تحقیق (`Researcher Node`) کوئری‌های ابزار Tavily را به‌صورت متوالی اجرا می‌کند به‌طوری که سرچ دوم بر اساس داده‌های سرچ اول شکل می‌گیرد. همچنین تقویم زنده شمسی و میلادی به کانتکست اضافه شد و سقف ۳ سرچ در سطح کد پایتون اعمال شد تا از لوپ بی‌نهایت جلوگیری شود.

2. **نگارش و سیستم جایگزین (Cascading Fallback):**
   برای مدیریت محدودیت نرخ (Rate Limit) یا قطعی شبکه، یک زنجیره ۵ مرحله‌ای با تاخیر فزاینده پیاده‌سازی شد:
   
   $$\text{Gemini 3.5 Flash (Deep Thinking)} \longrightarrow \text{Gemini 3 Flash} \longrightarrow \text{Gemini 3.1 Flash Lite}$$

   در بخش لحن نگارش، عبارت‌های کلیشه‌ای هوش مصنوعی فیلتر شده و لحن مقاله به سمت نقد فنی و ساده‌نویسی هدایت می‌شود. تصاویر موجود با فرمت `![alt](media_id:ID)` و تصاویر پیشنهادی با `![custom_alt_farsi](suggestion_id:LOCAL_ID)` نشانه‌گذاری می‌شوند.

---

### ورک‌فلو ۳: ساختار سئو و دسته‌بندی

![SEO Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972592/3_seo_workflow_jfxybz.png)

درخت دسته‌بندی‌های سایت به همراه توضیحات موضوعی به جمینای داده می‌شود. مدل بر اساس ساختار ارث‌بری متوجه می‌شود که انتخاب یک زیردسته به معنی تعلق مقاله به دسته والد نیز هست؛ بنابراین از انتخاب همزمان والد و فرزند خودداری کرده و ۱ تا ۳ دسته‌بندی اصلی را انتخاب می‌کند.

همچنین ساخت ۲ تا ۵ برچسب فارسی، `meta_title`، `meta_description` و اسلاگ فارسی روان انجام شده و مقاله به آدرس کانونیکال `/post/slug/` متصل می‌شود.

---

### ورک‌فلو ۴: ساخت تصویر و حل Race Condition

![Image Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972625/4_image_workflow_x4dbpt.png)

1. **انتخاب منبع تصویر:** برای محصولات یا افراد واقعی، تصویر از گوگل (Serper API) واکشی می‌شود و برای مفاهیم انتزاعی از مدل `ZImageTurbo` در deAPI استفاده می‌شود.
2. **لایه جایگزین:** به‌جای ساخت تصویر ساده با Pillow هنگام قطع سرویس، یک لایه دوگانه جایگزین شد: ابتدا تولید تصویر زنده با `Pollinations.ai` (مدل FLUX) و در صورت خطای شبکه، دانلود تصویر استاتیک از Unsplash.
3. **حل Race Condition در ذخیره‌سازی:**
   تسک انتشار Celery گاهی چند میلی‌ثانیه قبل از Commit شدن کوئری‌های تصویر اجرا می‌شد و پست بدون عکس می‌ماند. برای حل این مشکل، به‌روزرسانی‌های تصویر درون بلاک `with transaction.atomic()` با قفل `select_for_update()` قرار گرفت و فراخوانی تسک Celery به قلاب `transaction.on_commit` منتقل شد تا دقیقاً پس از ثبت نهایی داده‌ها روی دیتابیس اجرا شود.

---

### ورک‌فلو ۵: انتشار در وب و تلگرام

![Publisher Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972660/5_publisher_workflow_gmhiys.png)

1. **انتشار روی وب:** وضعیت مقاله به `PUBLISHED` تغییر کرده و بردار ۷۶۸ بعدی آن در مجموعه `contents` دیتابیس TurboVec ذخیره می‌شود.
2. **حل بن‌بست Event Loop در Celery:**
   کلاینت Telethon به‌صورت Async کار می‌کند اما ورکر Celery محیط Sync دارد. استفاده از `async_to_sync` در محیط داکر باعث قفل شدن نخ‌های Celery می‌شد. برای حل این موضوع، درون متد ارسال یک ایونت لوپ جدید (`asyncio.new_event_loop()`) ساخته شد، اجرا در `asyncio.wait_for` با مهلت ۶۰ ثانیه محدود شد و لوپ در بلاک `finally` بسته شد.
3. **انتشار در تلگرام:** جای‌گذاری لینک مقاله، تبدیل برچسب‌ها به هشتگ و ارسال پیام همراه آلبوم به کانال `@teknovia_ir`.

---

## فرانت‌اند، شبکه و تنظیمات کش

- **کنار گذاشتن هاردکد Vite در بیلد:** برای جلوگیری از ثبت متغیرهای `.env` در زمان بیلد آسترو (`npm run build`) که باعث خطای ۵۰۰ در داکر می‌شد، یک متد داینامیک تایپ‌اسکریپت نوشتم تا متغیرها را در زمان اجرا (Runtime) از `globalThis` بخواند.
- **رندر ویدیو:** در `Card.astro` و `[slug].astro` منطق رندر طوری تغییر کرد که فایل‌های ویدیویی به‌جای تگ `<img>` در تگ `<video autoplay loop muted playsinline>` نمایش داده شوند.
- **کشینگ ۵ دقیقه در CDN:** برای کش شدن صفحات HTML روی کلودفلر، هدر `Cache-Control: public, max-age=0, s-maxage=300` روی آسترو تنظیم شد و یک Cache Rule بر اساس `s-maxage` در کلودفلر تعریف گردید.

---

## تکنولوژی‌های استفاده‌شده

- **بک‌اند:** Python 3.13, Django 6.0, Celery 5.6, Redis 7, Telethon
- **موتور برداری:** FastAPI + TurboVec (ابعاد ۷۶۸)
- **فرانت‌اند:** Astro 7.0, SolidJS, Tailwind CSS v4
- **پایگاه داده:** PostgreSQL 18
- **مدل‌های هوش مصنوعی:** DeepSeek-V4 Pro/Flash, Google Gemini 3.5 Flash & Embedding 2, deAPI (Qwen NF4 & ZImage), Pollinations AI (FLUX)
- **زیرساخت:** Docker Compose (۷ کانتینر)، Nginx، Cloudflare CDN

---

## راه اندازی سریع

```bash
# کلون پروژه
git clone https://github.com/your-username/teknovia.git
cd /var/www/teknovia

# بیلد و اجرای کانتینرها
docker compose up -d --build

# مایگریشن و جمع‌آوری استاتیک‌ها
docker compose exec django-backend python manage.py migrate
docker compose exec django-backend python manage.py collectstatic --noinput

# ریلود Nginx
nginx -t && systemctl reload nginx
```

---

## لایسنس

این پروژه تحت لایسنس MIT منتشر شده است.

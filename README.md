# 🚀 تکنوویا (Teknovia) — خبرگزاری تمام‌خودکار و چندعاملی هوش مصنوعی
> **یک ماجراجویی مهندسی در طراحی سیستم‌های چندعاملی (Multi-Agent Architecture)، پردازش برداری ناهمگام و خط لوله تولید محتوای خودکار بر پایه فریم‌ورک‌های نسل جدید سال ۲۰۲۶.**

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Astro](https://img.shields.io/badge/Astro-7.0-BC52EE.svg?logo=astro&logoColor=white)](https://astro.build/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange.svg)](https://www.langchain.com/langgraph)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)

---

## 📖 داستان شکل‌گیری تکنوویا (Developer Journey)

پروژه **تکنوویا (Teknovia)** برای من صرفاً ساخت یک وب‌سایت خبری یا یک اسکریپت ساده جمع‌آوری اطلاعات نبود؛ بلکه یک ماجراجویی مهندسی عمیق برای پاسخ به این سوال بود: **«چطور می‌توان یک خبرگزاری کامل، تحلیلی، سئو شده و مالتی‌مدیا ساخت که ۲۴ ساعت شبانه‌روز بدون نیاز به حتی یک اپراتور انسانی، دقیق‌تر و سریع‌تر از تیم‌های خبری سنتی کار کند؟»**

برای حل این مسئله، سیستم‌های متداول مانند خط‌لوله‌های ساده (Pipelines) جوابگو نبودند. محتوای دنیای واقعی پیچیده است: شامل اسپم، اخبار تکراری، اسکرین‌شات‌های واترماک‌دار، لینک‌های خراب، عدم وجود تصاویر باکیفیت و ساختارهای غیرسئو می‌شود. 

پاسخ من به این چالش، طراحی یک **اکوسیستم چندعاملی (Multi-Agent System)** بر پایه فریم‌ورک **LangGraph**، معماری میکرو‌سرویس برای جستجوی برداری، و تلفیق هوشمندانه پیشرفته‌ترین مدل‌های هوش مصنوعی سال ۲۰۲۶ (از جمله DeepSeek-V4 و Gemini 3.5) بود.

---

## 🏗️ معماری کلان سیستم (Master Architecture)

سیستم از **۷ کانتینر ایزوله داکر** تشکیل شده که به صورت ناهمگام و رویدادمحور (Event-Driven) با هم در ارتباط هستند. پیام‌ها از کانال‌های تلگرامی واکشی شده، در دیتابیس PostgreSQL ثبت می‌شوند و سپس زنجیره‌ای از ۵ ورک‌فلوی هوشمند را طی می‌کنند:

```
[ Telegram Channels ] ──(Telethon Listener)──► [ PostgreSQL DB ]
                                                     │
                                           (Celery / Redis Queue)
                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 LANGGRAPH MULTI-AGENT ENGINE                            │
│                                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐  │
│  │ 1. Processor    │───►│ 2. Writer & Res.│───►│ 3. SEO Architect│───►│ 4. Image Gen │  │
│  │    Workflow     │    │    Workflow     │    │    Workflow     │    │   Workflow   │  │
│  └────────┬────────┘    └─────────────────┘    └─────────────────┘    └──────┬───────┘  │
└───────────┼──────────────────────────────────────────────────────────────────┼──────────┘
            │                                                                  │
            ▼                                                                  ▼
 [ FastAPI + TurboVec ]                                               [ 5. Publisher Workflow ]
(768d Vector Database)                                                          │
                                                               ┌────────────────┴──────────────┐
                                                               ▼                               ▼
                                                     [ Astro 7 Frontend ]     [ Telegram Channel ]
                                                    (teknovia.ir/post/...)      (@teknovia_ir)
```

### 🖼️ نماد گرافیکی معماری کلان (Master System Flow):
![Master Architecture](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972697/6_master_architecture_xjpibh.png)

---

## 🔄 چرخه حیات و ورک‌فلوهای پنج‌گانه عامل‌ها (The 5 Workflows)

### ۱. ورک‌فلوی پردازش خام و پالایش برداری (Processor Workflow)
![Processor Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972503/1_processor_workflow_tldqci.png)

* **شنود زنده و تجمیع آلبوم (Telethon Debouncing):** کلاینت Telethon پیام‌ها را رصد می‌کند. برای آلبوم‌های چندرسانه‌ای، سیستم با منطق Debounce چند ثانیه صبر کرده تا تمامی عکس‌ها و ویدیوهای دارای `grouped_id` یکسان را به صورت یکجا دریافت و دانلود کند.
* **فیلتر هرزنامه (Observer Node):** مدل `deepseek-v4-pro` متن ورودی را تحلیل کرده و تبلیغات، فروش VPN، پکیج‌های آموزشی و محتوای غیرتکنولوژی را اسکیپ می‌کند.
* **بررسی معنایی تکرار (Checker Node & TurboVec):**
  * متن خبر به مدل `gemini-embedding-2` ارسال شده و بردار ۷۶۸ بعدی آن تولید می‌شود.
  * بردار حاصل در مجموعه `received` دیتابیس TurboVec جستجو می‌شود.
  * **الگوریتم تصمیم‌گیری دو مرحله‌ای:**
    * اگر شباهت بالای **۹۲٪** باشد ➔ خبر تکراری تشخیص داده شده و بدون مصرف توکن اضافی حذف می‌شود.
    * اگر شباهت بین **۶۵٪ تا ۹۲٪** باشد ➔ کاندیداها به مدل `deepseek-v4-flash` ارجاع داده می‌شوند تا تصمیم نهایی درباره یکتا بودن خبر اتخاذ شود.
* **استخراج عمیق وب (Fetcher Node):** لینک‌های موجود در خبر با ابزار بومی `url_context` مدل `gemini-3.1-flash-lite` خلاصه‌سازی و تحلیل می‌شوند.
* **آنالیز مالتی‌مدیا و حذف واترماک (Analyzer & Image Editor):**
  * رسանه‌ها با `Gemini Vision` آنالیز شده و توضیحات متنی غنی برای عامل نویسنده ساخته می‌شود.
  * **سد دفاعی Anti-UI-Tampering:** به مدل آموزش داده شده تا عناصر تعاملی سایت‌ها (مثل دکمه‌ها و منوها) را دست‌نخورده نگه دارد و صرفاً آیدی کانال‌های رقیب یا لوگوهای واترمارک شده را شناسایی کند.
  * در صورت نیاز به پاک‌سازی، تصویر به مدل `QwenImageEdit_Plus_NF4` در deAPI فرستاده شده و تصویر تمیز شده جایگزین می‌گردد.

---

### ۲. ورک‌فلوی تحقیق و نگارش سردبیری (Writer & Research Workflow)
![Writer Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972565/2_writer_workflow_nykfyz.png)

* **ناظر نگارش (Supervisor Node):** تصمیم می‌گیرد اطلاعات ورودی کامل است یا نیاز به تحقیق وب دارد.
* **تحقیق زنجیره‌ای و متوالی (Sequential Adaptive Search):**
  * عامل تحقیقگر (`Researcher Node`) موظف است کوئری‌های خود را به صورت **تک‌به‌تک و متوالی** بر پایه نتایج جستجوی قبلی اجرا کند (حداکثر ۳ سرچ با ابزار Tavily).
  * **تزریق زمان جاری (2026 Calendar Anchor):** برای جلوگیری از خطای تاریخی مدل‌ها، تاریخ زنده میلادی و شمسی سال ۲۰۲۶ به کانتکست تزریق می‌شود.
* **زنجیره فال‌بک نویسنده (Cascading Fallback Chain):**
  برای مهار خطاهای ریت‌لیمیت شبکه، سیستم نویسندگی از یک الگوی زنجیره‌ای ۵ تلاشی با Backoff استفاده می‌کند:
  $$\text{Gemini 3.5 Flash + Deep Thinking} \longrightarrow \text{Gemini 3 Flash} \longrightarrow \text{Gemini 3.1 Flash Lite}$$
* **پروتکل انسجام انسانی (Humanizer Protocol):**
  فیلتر سخت‌گیرانه ادبیات AI (حذف عباراتی نظیر *«شایان ذکر است»*، *«چشم‌انداز»*، *«در دنیای امروز»*) و تزریق روحیه نقد فنی و لحن جذاب خبرنگاری.
* **تگ‌گذاری تصاویر:** نویسنده از ساختار `![alt](media_id:ID)` برای عکس‌های موجود و `![custom_alt_farsi](suggestion_id:LOCAL_ID)` برای تصاویر پیشنهادی جدید استفاده می‌کند.

---

### ۳. ورک‌فلوی بهینه‌سازی سئو (SEO Architecture Workflow)
![SEO Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972592/3_seo_workflow_jfxybz.png)

* **درک ساختار درختی و ارث‌بری دسته‌ها (Taxonomy Inheritance):** 
  درخت دسته‌بندی‌های سایت به همراه توضیحات موضوعی به جمینای داده می‌شود. مدل درک می‌کند که اتصال مقاله به زیردسته به معنی تعلق به دسته والد است؛ بنابراین از انتخاب همزمان والد و فرزند خودداری کرده و **۱ تا ۳ دسته اصلی** مرتبط را انتخاب می‌کند.
* **تولید برچسب و متادیتا:** انتخاب **۲ تا ۵ برچسب اسم‌محور و تمیز فارسی**، ساخت `meta_title` (زیر ۷۰ کاراکتر)، `meta_description` (زیر ۱۶۰ کاراکتر) و اسلاگ فارسی سئو شده.
* **اتصال اتمیک (M2M Sync):** ثبت داده‌ها در PostgreSQL و تنظیم آدرس کانونیکال بر پایه روت نوین `/post/slug/`.

---

### ۴. ورک‌فلوی پردازش و تولید تصاویر پیشنهادی (Image Workflow)
![Image Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972625/4_image_workflow_x4dbpt.png)

* **سوپروایزر تصویر:** تصمیم می‌گیرد تصویر پیشنهادی باید از وب جستجو شود (محصولات واقعی، برندها یا اشخاص با Serper API) یا به صورت هنری تولید شود (`ZImageTurbo_INT8` در deAPI).
* **سیستم فال‌بک فوق‌العاده باکیفیت پروداکشن (منسوخ کردن Pillow):**
  در صورت شکست deAPI، سیستم به صورت خودکار به **موتور رایگان و بدون محدودیت `Pollinations.ai` (بر پایه مدل FLUX)** سوئیچ کرده و تصویر زنده را تولید می‌کند. در صورت خطای شبکه، یک تصویر استاتیک باکیفیت فناوری از **Unsplash** دانلود می‌گردد.
* **استخراج Alt Text با Regex:** متن آلت فارسی از مارک‌داون استخراج شده و تگ `suggestion_id` اتمیک به `media_id` واقعی تغییر می‌یابد.

---

### ۵. ورک‌فلوی انتشار متمرکز (Publisher Workflow)
![Publisher Workflow](https://res.cloudinary.com/dwy6ves9w/image/upload/v1784972660/5_publisher_workflow_gmhiys.png)

* **انتشار وب‌سایت و ایندکس برداری:** مقاله در وب‌سایت منتشر شده (`PUBLISHED`)، امبدینگ ۷۶۸ بعدی آن توسط `gemini-embedding-2` محاسبه شده و در مجموعه `contents` دیتابیس TurboVec ذخیره می‌شود (جهت استفاده در سیستم مقالات مشابه و جلوگیری از تکرار).
* **انتشار تلگرام (Telethon):**
  * جای‌گذاری هایپرلینک متنی مخفی `[جزئیات بیشتر...](url)` به جای تگ نگهدارنده `<!-- MAIN_ARTICLE_URL -->`.
  * تبدیل خودکار اسلاگ برچسب‌ها به هشتگ تلگرامی (مانند `#کارت_گرافیک`).
  * تبدیل مارک‌داون به HTML استاندارد تلگرام و ارسال آلبوم رسانه‌ها با Telethon.

---

## 💡 تصمیمات عمیق مهندسی و چالش‌های سخت برطرف‌شده

### ۱. چرا پایگاه‌داده برداری (TurboVec) به صورت یک سرویس مجزای FastAPI پیاده‌سازی شد؟
به جای نصب افزونه‌های سنگین برداری روی دیتابیس اصلی (مانند pgvector) یا قرار دادن مستقیم متدهای پایتونی در جنگو، یک میکرو‌سرویس مستقل تحت **FastAPI** توسعه داده شد.
* **عدم مسدودسازی Event Loop جنگو (Non-Blocking):** محاسبات سنگین ریاضی و ضرب داخلی ماتریس‌ها (Numpy) از نخ‌های پردازش درخواست‌های HTTP جنگو جدا شد.
* **مدیریت بهینه حافظه RAM:** الگوریتم فشرده‌سازی برداری (TurboQuant) بردارها را با دقت ۴ بیتی در حافظه رم FastAPI نگه می‌دارد و نوسانات پردازشی آن تاثیری روی وب‌سرویس اصلی ندارد.
* **ارتباط دو دیتابیس (Dual-DB Linking):** جهت حفظ یکپارچگی ارجاعات، شناسه دیتابیس جنگو (`django_id`) به عنوان نگاشت در FastAPI ذخیره شده و شناسه برداری (`external_id`) در دیتابیس PostgreSQL ثبت می‌شود.

### ۲. مهار مسابقه داده‌ای (Race Condition) با `transaction.on_commit`
یکی از چالش‌های سخت سیستم، بیدار شدن زودهنگام تسک‌های سلری قبل از Commit فیزیکی داده‌های تصویر روی دیسک بود. با بازنویسی کدها بر پایه **`with transaction.atomic()`** و استفاده از قفل‌های **`select_for_update()`**، فراخوانی تسک انتشار سلری به قلاب بومی **`transaction.on_commit`** منتقل شد تا تنها پس از ذخیره‌سازی قطعی کوئری‌ها روی هارد، اجرا شود.

### ۳. حل باگ فریز شدن و بن‌بست Event Loop در ترکیب Celery و Telethon
فراخوانی توابع ناهمگام Telethon درون کارهای همگام سلری باعث بروز Deadlock می‌شد. این چالش با ایجاد یک **حلقه رویداد مستقل (`asyncio.new_event_loop`)** درون نخ فعال سلری و اعمال سقف زمانی قطعی **`asyncio.wait_for` (۶۰ ثانیه)** برطرف شد تا کانتینر سلری هرگز دچار قفل نشود.

### ۴. فرار از بهینه‌ساز بیلد ویت (Vite Build-time Inlining Bypass)
موتور Vite در زمان ساخت کدهای آسترو (`npm run build`) متغیرهای محیطی `process.env` را در فایل‌های جاوااسکریپت هاردکد می‌کرد. با پیاده‌سازی متد داینامیک تایپ‌اسکریپت در `api.ts` با بررسی `globalThis` در زمان اجرا (Runtime)، آدرس‌های شبکه داخلی داکر بدون نیاز به بیلد مجدد خوانده می‌شوند.

---

## 🛠️ تک‌استک و تکنولوژی‌های به‌روز (Tech Stack - 2026 Upgrades)

* **بک‌اند وب‌سرویس‌ها:** Python 3.13, Django 6.0 (Async-First ORM), Celery 5.6, Redis 7.
* **سرویس برداری (Vector DB):** FastAPI + TurboVec (ابعاد ۷۶۸، الگوریتم TurboQuant).
* **فرانت‌اند و رندرینگ:** Astro 7.0 (موتور Rolldown و کامپایلر Rust)، SolidJS (Interactive Islands)، Tailwind CSS v4 (موتور Oxide، پالت رنگی OKLCH در `global.css`).
* **پردازشگر مارک‌داون فرانت‌اند:** Sätteri (نوشته شده با زبان Rust).
* **پایگاه داده اصلی:** PostgreSQL 18.
* **مدل‌های هوش مصنوعی (LLMs):**
  * DeepSeek-V4 Pro & Flash (پایش اولیه، فیلتر اسپم و بررسی تشابه)
  * Google Gemini 3.5 Flash, Gemini 3 Flash & 3.1 Flash Lite (نگارش، خلاصه‌سازی و سئو)
  * Gemini Embedding 2 (تولید بردارهای چندرسانه‌ای با ابعاد ۷۶۸)
  * deAPI / QwenImageEdit_Plus_NF4 & ZImageTurbo_INT8 (ادیت و تولید عکس)
  * Pollinations AI / FLUX & Unsplash (لایه فال‌بک تصویر)
* **زیرساخت و DevOps:** Docker Compose (۷ کانتینر ایزوله)، Nginx (پیکربندی `alias` مستقیم برای رسانه‌ها)، Cloudflare CDN (Edge TTL `s-maxage=300` برای HTML و ۱ ساله برای استاتیک‌ها).

---

## 🚀 راهنمای راه‌اندازی و استقرار (Deployment Guide)

### پیش‌نیازها
* سرور لینوکس (Ubuntu 24.04 LTS recommended)
* Docker & Docker Compose
* دامنه فعال و تنظیم‌شده روی Cloudflare

### ۱. کلون کردن مخزن و تنظیم متغیرهای محیطی
```bash
git clone https://github.com/your-username/teknovia-ai-agency.git
cd teknovia-ai-agency

# تنظیم متغیرهای محیطی اصلی
cp AI-Agency/.env.example .env
```

### ۲. بیلد و اجرای کانتینرهای داکر
```bash
docker compose up -d --build
```

### ۳. جمع‌آوری استاتیک‌ها و مایگریشن دیتابیس
```bash
docker compose exec django-backend python manage.py migrate
docker compose exec django-backend python manage.py collectstatic --noinput
```

### ۴. پیکربندی Nginx و SSL
فایل پیکربندی موجود در کدهای پروژه را در مسیر `/etc/nginx/sites-available/teknovia` کپی کرده و Nginx را ریلود کنید:
```bash
nginx -t && systemctl reload nginx
```

---

## ⚡ دستورات کاربردی سرور (Cheatsheet)

* **مشاهده لاگ‌های زنده ورکر سلری:**
  ```bash
  docker compose logs -f --tail=50 celery_worker
  ```
* **مشاهده لاگ‌های زنده سرویس برداری:**
  ```bash
  docker compose logs -f --tail=50 vector_fastapi
  ```
* **پاک‌سازی هوشمند کش دیسک داکر (جهت مدیریت فضای سرور):**
  ```bash
  docker system prune -af --volumes
  ```

---

## 📝 لایسنس و حقوق مالکیت
این پروژه تحت لایسنس **MIT** منتشر شده است. تمامی حقوق برند و نام تجاری **تکنوویا (Teknovia)** محفوظ می‌باشد.

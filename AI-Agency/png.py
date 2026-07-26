# /var/www/teknovia/AI-Agency/generate_diagrams.py
import os
import io
import base64
import requests
from PIL import Image

# ایجاد دایرکتوری ذخیره‌سازی تصاویر گراف‌ها
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "docs", "diagrams")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ────────────────────────────────────────────────────────────────
# تعریف کدهای اصلاح‌شده Mermaid با پوشش کامل کوتیشن‌ها و کاراکترها
# ────────────────────────────────────────────────────────────────

DIAGRAMS = {
    # ۱. ورک‌فلوی پردازش اولیه و مانیتورینگ
    "1_processor_workflow": """
    graph TD
        A["Telegram Channel"] -->|Telethon Listener| B("ReceivedMessages DB")
        B --> C{"Observer Node: DeepSeek-V4 Pro"}
        C -->|Spam / Ads| END_SPAM["END: Skip & Mark Finished"]
        C -->|Relevant Tech News| D{"Checker Node: DeepSeek-V4 Flash"}
        D -->|Vector Search| TV_REC[("TurboVec: received Collection")]
        TV_REC -->|Similarity Over 92 Percent| END_DUP["END: Duplicate News Skipped"]
        D -->|Unique News| E["Fetcher Node: Gemini 3.1 Flash Lite"]
        E -->|Native Tool| URL_CTX["Google URL Context Tool"]
        URL_CTX -->|Summarized Web Contents| F["Analyzer Node: Gemini Vision"]
        F -->|Anti-UI-Tampering Guardrail| MEDIA_CHK{"Needs Watermark Edit?"}
        MEDIA_CHK -->|Yes| G["Image Editor Node: deAPI QwenImageEdit"]
        MEDIA_CHK -->|No| H["Saver Node: TurboVec Indexer"]
        G -->|Cleaned Image| H
        H -->|Save Embeddings| TV_REC
        H -->|Trigger Task 2| NEXT["Celery: process_writing_workflow"]
    """,

    # ۲. ورک‌فلوی تحقیق و نگارش سردبیری
    "2_writer_workflow": """
    graph TD
        START["Celery Task: process_writing_workflow"] --> SUP{"Supervisor Node: DeepSeek-V4 Flash"}
        SUP -->|Decision: Skip| END_SKIP["END: Skipped"]
        SUP -->|Decision: Write| WRITER["Writer Node: Gemini Cascading Fallback"]
        SUP -->|Decision: Research| RES["Researcher Node: Sequential Adaptive Search"]

        RES -->|Inject 2026 Calendar Anchor| TAVILY["Tavily Search Tool"]
        TAVILY -->|Step-by-step query 1, 2, 3| RES
        RES -->|Complete Research Context| WRITER

        subgraph Writer Cascading Fallback
            WRITER -->|Attempt 1| M1["Gemini 3.5 Flash + Deep Thinking"]
            M1 -->|Fail / RateLimit| M2["Gemini 3 Flash"]
            M2 -->|Fail / RateLimit| M3["Gemini 3.1 Flash Lite"]
        end

        M1 -->|Structured Output| SAVER["Saver Node: PostgreSQL"]
        M2 -->|Structured Output| SAVER
        M3 -->|Structured Output| SAVER

        SAVER -->|Create Draft| CONTENT_DB[("PostgreSQL: Content Article")]
        SAVER -->|Create Draft| POST_DB[("PostgreSQL: PostsContainer Telegram")]
        SAVER -->|Dispatch Task 3| SEO_TASK["Celery: process_seo_workflow"]
        SAVER -->|Dispatch Images| IMG_DISP["Celery: dispatch_pending_image_suggestions"]
    """,

    # ۳. ورک‌فلوی بهینه‌سازی سئو و معماری محتوا
    "3_seo_workflow": """
    graph TD
        START["Celery Task: process_seo_workflow"] --> ANALYZER["SEO Analyzer Node: Gemini 3.1 Flash Lite"]
        ANALYZER -->|Fetch Active Categories| CAT_TREE["Category Hierarchy & Scope Descriptions"]
        ANALYZER -->|Fetch Existing Tags| TAG_DB["Django Tag Model"]

        CAT_TREE --> ANALYZER
        TAG_DB --> ANALYZER

        ANALYZER -->|Select 1-3 Categories with Inheritance| OUT1["Selected Category IDs"]
        ANALYZER -->|Select 2-5 Clean Noun Tags| OUT2["Selected Tags"]
        ANALYZER -->|SEO Metadata| OUT3["Meta Title, Meta Description & Farsi Slug"]

        OUT1 --> SAVER["SEO Saver Node"]
        OUT2 --> SAVER
        OUT3 --> SAVER

        SAVER -->|Save Canonical URL /post/slug/| CONTENT_DB[("PostgreSQL: Content")]
        SAVER -->|Atomic M2M Sync| TAG_REL[("PostgreSQL: Category & Tag Relations")]
    """,

    # ۴. ورک‌فلوی پردازش و تولید تصاویر
    "4_image_workflow": """
    graph TD
        START["Celery Task: process_image_suggestion_task"] --> SUP{"Image Supervisor Node: DeepSeek-V4 Flash"}
        SUP -->|Decision: find| FINDER["Image Finder Node: Serper API"]
        SUP -->|Decision: generate| GEN["Image Generator Node: deAPI ZImageTurbo"]

        FINDER -->|Google Image Search| CANDIDATES["Download & Compress Candidates"]
        CANDIDATES --> GEMINI_SEL["Gemini 3.1 Flash Lite Selection"]
        GEMINI_SEL -->|Matched Real Photo| SAVER["Image Saver Node"]
        GEMINI_SEL -->|No Match| GEN

        subgraph Image Generation & Production Fallback
            GEN -->|Poll Job Status| DEAPI_API["deAPI Cloud"]
            DEAPI_API -->|Fail / Timeout| POLLINATIONS["Pollinations.ai FLUX API"]
            POLLINATIONS -->|Network Fail| UNSPLASH["Unsplash High-Res Tech Stock"]
        end

        DEAPI_API --> SAVER
        POLLINATIONS --> SAVER
        UNSPLASH --> SAVER

        SAVER -->|Regex Alt Text Extraction| REGEX["Match Markdown suggestion_id"]
        REGEX -->|Replace with media_id| DB_SAVE[("PostgreSQL: MediaContainer & Content")]
        DB_SAVE -->|transaction.on_commit| PUB_TASK["Celery: process_publisher_workflow"]
    """,

    # ۵. ورک‌فلوی انتشار متمرکز
    "5_publisher_workflow": """
    graph TD
        START["Celery Task: process_publisher_workflow"] --> PUB1["Article Publisher Node"]
        PUB1 -->|Set Status to PUBLISHED| CONTENT_DB[("PostgreSQL: Content")]
        PUB1 -->|Generate Vector| EMBED["Gemini Embedding 2: 768 Dimensions"]
        EMBED -->|Index Document| TV_CONTENTS[("TurboVec: contents Collection")]

        PUB1 --> PUB2["Telegram Publisher Node"]
        PUB2 -->|Replace MAIN_ARTICLE_URL| URL_INJECT["Hyperlink: جزئیات بیشتر... (URL)"]
        PUB2 -->|Slug to Hashtags| TAG_INJECT["Hashtags: #کارت_گرافیک"]
        PUB2 -->|Convert Markdown| HTML_FMT["Telegram Standard HTML"]

        HTML_FMT --> TELETHON["Telethon Async Client: asyncio.new_event_loop"]
        TELETHON -->|Send Album + Caption| TG_CHAN["Telegram Channel: @teknovia_ir"]
        TG_CHAN -->|Success| SENT_STATE["PostsContainer State -> SENT"]
    """,

    # ۶. گراف کلان معماری سیستم (Master Architecture)
    "6_master_architecture": """
    graph TB
        subgraph External Inputs
            TG_IN["Monitored Telegram Channels"]
        end

        subgraph Workflow 1: Processor
            W1_OBS["Observer: Spam Filter"]
            W1_CHK["Checker: Duplication Check"]
            W1_FETCH["Fetcher: Gemini url_context"]
            W1_VIS["Analyzer: Vision & Watermarks"]
            W1_EDIT["Image Editor: Qwen NF4"]
        end

        subgraph Workflow 2: Writer & Research
            W2_SUP["Supervisor"]
            W2_RES["Sequential Researcher: Tavily"]
            W2_WRITE["Writer: Gemini Fallback Chain"]
        end

        subgraph Workflow 3: SEO Architecture
            W3_SEO["Taxonomy & Metadata Architect"]
        end

        subgraph Workflow 4: Image Generator
            W4_IMG["Serper / deAPI / Pollinations FLUX Fallback"]
        end

        subgraph Workflow 5: Publisher
            W5_PUB["TurboVec Indexer & Telethon Publisher"]
        end

        subgraph Infrastructure
            PG[("PostgreSQL 18")]
            REDIS[("Redis 7 Cache")]
            CELERY["Celery Workers"]
            FASTAPI["FastAPI + TurboVec Vector DB"]
            NGINX["Nginx Server"]
            ASTRO["Astro 7 Frontend"]
            CDN["Cloudflare CDN"]
        end

        TG_IN -->|Telethon Listener| W1_OBS
        W1_OBS --> W1_CHK
        W1_CHK <--> FASTAPI
        W1_CHK --> W1_FETCH --> W1_VIS --> W1_EDIT
        W1_EDIT -->|Celery Queue| CELERY

        CELERY --> W2_SUP --> W2_RES --> W2_WRITE
        W2_WRITE -->|Draft Save| PG
        W2_WRITE -->|Celery Trigger| W3_SEO
        W2_WRITE -->|Celery Trigger| W4_IMG

        W3_SEO -->|SEO Meta Sync| PG
        W4_IMG -->|Alt Text & Media Sync| PG

        W4_IMG -->|transaction.on_commit| W5_PUB
        W5_PUB <--> FASTAPI
        W5_PUB -->|Publish Post| TG_IN

        ASTRO <--> NGINX <--> CDN <--> USERS(("End Users"))
        ASTRO <--> PG
    """
}


# ────────────────────────────────────────────────────────────────
# تابع تبدیل کدهای Mermaid به تصاویر PNG شفاف و باکیفیت
# ────────────────────────────────────────────────────────────────

def generate_png_from_mermaid(name: str, mermaid_code: str):
    """
    ارسال کد گراف به وب‌سرویس Mermaid.ink و ذخیره‌سازی تصویر PNG خروجی
    """
    print(f"🔄 در حال تولید نمودار: {name} ...")

    clean_code = mermaid_code.strip()
    graph_bytes = clean_code.encode('utf-8')
    base64_str = base64.b64encode(graph_bytes).decode('utf-8')

    # ساخت URL درخواست تصویر با کیفیت بالا از سرویس Mermaid
    image_url = f"https://mermaid.ink/img/{base64_str}?bgColor=!white"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(image_url, headers=headers, timeout=30)
        if response.status_code == 200:
            file_path = os.path.join(OUTPUT_DIR, f"{name}.png")

            # ذخیره بایت‌های تصویر
            img = Image.open(io.BytesIO(response.content))
            img.save(file_path, "PNG", optimize=True)

            print(f"✅ نمودار با موفقیت ذخیره شد: {file_path}")
        else:
            print(f"❌ خطا در تولید نمودار {name}: کد پاسخی {response.status_code}")
    except Exception as e:
        print(f"❌ خطای استثنا در زمان دریافت تصویر نمودار {name}: {e}")


if __name__ == "__main__":
    print("🚀 شروع فرآیند تولید خودکار تصاویر گراف‌های معماری تکنوویا...\n")
    for name, code in DIAGRAMS.items():
        generate_png_from_mermaid(name, code)
    print(f"\n✨ تمامی تصاویر گراف‌ها با موفقیت در مسیر زیر ایجاد شدند:\n{OUTPUT_DIR}")
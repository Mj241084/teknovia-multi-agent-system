# workflows/management/commands/run_telethon.py

import os
import re
import asyncio
import logging
from django.core.management.base import BaseCommand
from django.core.files import File
from django.db import transaction
from asgiref.sync import sync_to_async
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.extensions import markdown  # ماژول رسمی تلتون برای تبدیل پیوندهای متنی به مارک‌داون
from workflows.tasks import process_received_message

# ایمپورت مدل‌های پروژه
from contents.models import MediaContainer
from workflows.models import ReceivedMessages

logger = logging.getLogger(__name__)

API_ID_ENV = os.getenv('TELEGRAM_APP_ID')
API_HASH = os.getenv('TELEGRAM_APP_HASH')
SESSION_ENV = os.getenv('TELEGRAM_SESSION')

CHANNELS_LIST = [
    '@geetnews',
]

DOWNLOAD_BASE_DIR = './telegram_downloads'
TEMP_DIR = os.path.join(DOWNLOAD_BASE_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)


def extract_links_from_text(text: str) -> str:
    """
    استخراج و تفکیک تمام لینک‌های وب موجود در بدنه مارک‌داون پیام تلگرام.
    این تابع آدرس‌های درون کروشه و پرانتزهای مارک‌داون را به صورت کاملاً تمیز پاک‌سازی می‌کند.
    """
    if not text:
        return ""
    # استخراج تمام کاندیداهای لینک وب
    urls = re.findall(r'https?://[^\s\)]+', text)

    clean_urls = []
    for url in urls:
        # حذف کاراکترهای پرت پایانی مارک‌داون نظیر پرانتز بسته، کروشه یا علائم نگارشی
        url_clean = url.rstrip(').,]>')
        if url_clean and url_clean not in clean_urls:
            clean_urls.append(url_clean)

    return "\n".join(clean_urls) if clean_urls else ""


def get_formatted_markdown_text(message_obj) -> str:
    """
    تبدیل متن ساده تلگرام به همراه موجودیت‌های مخفی (مانند Hyperlinks)
    به متن غنی مارک‌داون جهت حفظ لینک‌های متنی نظیر [جزئیات بیشتر](url)
    """
    if not message_obj:
        return ""
    raw_text = message_obj.raw_text or ""
    entities = message_obj.entities

    if not entities:
        return raw_text

    try:
        # ان‌پارس کردن بومی تلتون بر اساس انکودینگ UTF-16 تلگرام جهت پیش‌گیری از باگ جابجایی آفست‌ها
        return markdown.unparse(raw_text, entities)
    except Exception as e:
        logger.warning(f"Error unparsing telegram entities to markdown: {e}")
        return message_obj.message or ""


def get_valid_media_type(event):
    """
    بررسی معتبر بودن رسانه:
    - تصویر: مجاز (برگشت نوع 'image')
    - ویدیو: مجاز فقط در صورتی که حجم کمتر یا مساوی ۵۰ مگابایت باشد (برگشت نوع 'video')
    - سایر فایل‌ها (داکیومنت‌ها، فشرده و...) یا ویدیوهای بالای ۵۰MB: غیرمجاز (برگشت None)
    """
    if not event.media:
        return None
    if event.photo:
        return 'image'
    if event.video:
        if event.file and (event.file.size / (1024 * 1024)) <= 50:
            return 'video'
    return None


@transaction.atomic
def save_telegram_message_to_db(text, media_files_info, telegram_group_id=None):
    """
    ذخیره‌سازی پیام و پیوست‌های دانلود شده به صورت یکجا و فراخوانی ایمن تسک سلری پس از ثبت تراکنش دیتابیس
    """
    links = extract_links_from_text(text)

    # پیام یکجا ثبت می‌شود و مرحله آن به طور پیش‌فرض روی OBSERVING قرار می‌گیرد
    received_msg = ReceivedMessages.objects.create(
        raw_text=text or "",
        links=links,
        is_tech=False,
        is_exists=False,
        step=ReceivedMessages.Steps.OBSERVING,
        telegram_group_id=telegram_group_id
    )

    # اتصال فایل‌های دانلود شده
    for info in media_files_info:
        local_path = info['local_path']
        media_type = info['media_type']
        filename = info['filename']
        size_kb = info['size_kb']
        source_url = info['source_url']

        if os.path.exists(local_path):
            with open(local_path, 'rb') as f:
                django_file = File(f)

                media_container = MediaContainer(
                    media_type=media_type,
                    source_url=source_url or None,
                    original_size_kb=size_kb,
                    is_used=False,
                )
                media_container.media.save(filename, django_file, save=True)
                received_msg.medias.add(media_container)

    # 🟢 فرستادن پیام به تسک پس‌زمینه سلری فقط پس از Commit کامل و قطعی تراکنش در پایگاه‌داده
    transaction.on_commit(lambda: process_received_message.delay(received_msg.id))

    return received_msg


django_save_async = sync_to_async(save_telegram_message_to_db, thread_sensitive=True)


class Command(BaseCommand):
    help = 'Monitors Telegram channels, aggregates albums, converts rich hyperlinks to markdown, and saves to DB'

    def handle(self, *args, **options):
        if not all([API_ID_ENV, API_HASH, SESSION_ENV]):
            self.stdout.write(self.style.ERROR(
                "خطا: متغیرهای محیطی تلگرام تنظیم نشده‌اند."
            ))
            return

        self.stdout.write(self.style.SUCCESS("در حال آماده‌سازی کلاینت تلتون..."))
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("کلاینت متوقف شد."))

    async def main(self):
        api_id = int(API_ID_ENV)
        api_hash = API_HASH

        # قفل دانلود سریالی برای عدم جریمه سرعت از سمت تلگرام
        download_lock = asyncio.Lock()

        # دیکشنری برای جمع‌آوری موقت اجزای آلبوم‌ها در رم
        active_albums = {}

        if len(SESSION_ENV) > 50:
            client = TelegramClient(StringSession(SESSION_ENV), api_id, api_hash)
        else:
            client = TelegramClient(SESSION_ENV, api_id, api_hash)

        @client.on(events.NewMessage(chats=CHANNELS_LIST))
        async def new_message_handler(event):
            # بازسازی غنی متن پیام تلگرام به همراه کدهای مارک‌داون برای حفظ پیوندهای مخفی متنی
            text = get_formatted_markdown_text(event.message)
            grouped_id = getattr(event.message, 'grouped_id', None)

            if not text and not event.media:
                return

            # پیاده‌سازی الگوریتم جمع‌آوری آلبوم (Debounce)
            if grouped_id:
                if grouped_id in active_albums:
                    # این جزء از آلبوم را به لیست اضافه کرده و اجرای این رویداد را در همینجا تمام می‌کنیم
                    active_albums[grouped_id].append((event, text))
                    self.stdout.write(f"پارت جدید آلبوم {grouped_id} دریافت شد. اضافه به صف موقت.")
                    return
                else:
                    # ایجاد صف جدید در دیکشنری
                    active_albums[grouped_id] = [(event, text)]
                    self.stdout.write(f"شروع آلبوم جدید با شناسه {grouped_id}. ۲ ثانیه انتظار برای دریافت کل آلبوم...")
                    # ۲ ثانیه منتظر دریافت سایر پارت‌ها می‌مانیم
                    await asyncio.sleep(2.0)
                    # بازیابی کل پیام‌های جمع‌آوری شده برای این گروه
                    events_list_tuples = active_albums.pop(grouped_id, [(event, text)])
                    events_list = [t[0] for t in events_list_tuples]
            else:
                # پیام تکی عادی (نیازی به انتظار ندارد)
                events_list = [event]

            # پس از اطمینان از تجمیع کامل پارت‌های آلبوم، فرآیند دانلود و ذخیره شروع می‌شود
            await process_events_group(events_list, grouped_id)

        async def process_events_group(events_list, telegram_group_id=None):
            self.stdout.write(f"شروع پردازش دسته پیام‌ها (تعداد کل پارت‌ها: {len(events_list)})")

            # ۱. یافتن کپشن اصلی مارک‌داون شده (معمولاً کپشن آلبوم فقط روی یکی از پارت‌ها ثبت می‌شود)
            text = ""
            for ev in events_list:
                formatted_txt = get_formatted_markdown_text(ev.message)
                if formatted_txt:
                    text = formatted_txt
                    break

            # ۲. ساخت لینک منبع از اولین پارت معتبر
            source_url = None
            first_ev = events_list[0]
            try:
                chat = await first_ev.get_chat()
                username = getattr(chat, 'username', None)
                if username:
                    source_url = f"https://t.me/{username}/{first_ev.message.id}"
                else:
                    clean_id = str(first_ev.chat_id).replace('-100', '')
                    source_url = f"https://t.me/c/{clean_id}/{first_ev.message.id}"
            except Exception as e:
                pass

            media_files_info = []
            temp_files_to_delete = []

            # ۳. بررسی و فیلتر کردن فایل‌ها برای دانلود
            for ev in events_list:
                if not ev.media:
                    continue

                # بررسی اعتبار نوع فایل
                media_type = get_valid_media_type(ev)

                if media_type is None:
                    # اگر فایل متفرقه (پی‌دی‌اف، فایل زیپ و...) یا ویدیوی بالای ۵۰ مگابایت باشد
                    self.stdout.write(
                        self.style.WARNING(
                            f"-> رسانه پیام {ev.message.id} غیرمجاز بود (ویدیو بالای ۵۰MB یا فایل متفرقه). دانلود اسکیپ شد.")
                    )
                    continue

                # دانلود نوبتی رسانه‌های مجاز
                try:
                    self.stdout.write(f"-> پیام {ev.message.id} در صف دانلود {media_type} قرار گرفت...")
                    async with download_lock:
                        self.stdout.write(f"-> شروع دانلود {media_type} پیام {ev.message.id}...")
                        path = await ev.download_media(file=TEMP_DIR)

                    if path and os.path.exists(path):
                        temp_files_to_delete.append(path)
                        filename = os.path.basename(path)
                        size_kb = round(os.path.getsize(path) / 1024)
                        media_files_info.append({
                            'local_path': path,
                            'media_type': media_type,
                            'filename': filename,
                            'size_kb': size_kb,
                            'source_url': source_url
                        })
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"خطا در دانلود رسانه پیام {ev.message.id}: {e}"))

            # ۴. ثبت یکجا در دیتابیس جنگو (وقتی تمام دانلودها با موفقیت پایان یافت)
            try:
                received_msg = await django_save_async(text, media_files_info, telegram_group_id)
                self.stdout.write(self.style.SUCCESS(
                    f"ثبت با وضعیت Observing تکمیل شد. شناسه پیام: {received_msg.id} | تعداد رسانه‌های اضافه شده: {len(media_files_info)}"
                ))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"خطا در ذخیره‌سازی نهایی تراکنش دیتابیس: {e}"))
            finally:
                # پاکسازی فایل‌های موقت محلی
                for path in temp_files_to_delete:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception as ex:
                            self.stdout.write(self.style.WARNING(f"حذف فایل موقت {path} ناموفق بود: {ex}"))

        await client.start()
        self.stdout.write(self.style.SUCCESS(
            f"کلاینت فعال شد و کانال‌های مانیتور شده را رصد می‌کند:\n{CHANNELS_LIST}"
        ))
        await client.run_until_disconnected()
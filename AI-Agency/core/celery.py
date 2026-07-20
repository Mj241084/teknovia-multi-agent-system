# core/celery.py

import os
from celery import Celery

# تنظیم ماژول پیش‌فرض تنظیمات جنگو برای ابزار سلری
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# خواندن پیکربندی‌های سلری از تنظیمات جنگو با پیشوند CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# شناسایی خودکار تمام تسک‌های نوشته شده در برنامه‌ها (مانند tasks.py)
app.autodiscover_tasks()
FROM python:3.13-slim
WORKDIR /app

# جلوگیری از نوشتن فایل‌های کش pyc و فعال‌سازی لاگ زنده
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# نصب ابزارهای مورد نیاز سیستم‌عامل برای پکیج‌های پایتون
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001
CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
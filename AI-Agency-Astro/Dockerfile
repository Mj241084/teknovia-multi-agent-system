# استفاده از نسخه سبک و پایدار نود اس ۲۰۲۶
FROM node:20-alpine AS builder
WORKDIR /app

# کپی فایل‌های پیکربندی پکیج‌ها
COPY package*.json ./
RUN npm ci

# کپی کل کدهای فرانت‌اند و ساخت بیلد پروداکشن
COPY . .
RUN npm run build

# مرحله اجرای نهایی وب‌سرور آسترو
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./package.json

EXPOSE 3000
ENV HOST=0.0.0.0
ENV PORT=3000

CMD ["node", "./dist/server/entry.mjs"]
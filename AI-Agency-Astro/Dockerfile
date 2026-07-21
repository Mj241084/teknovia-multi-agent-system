# استفاده از نسخه پایدار و مدرن Node.js 22 مورد نیاز آسترو ۷
FROM node:22-alpine AS builder
WORKDIR /app

# کپی فایل‌های پیکربندی پکیج‌ها
COPY package*.json ./
RUN npm ci

# کپی کل کدهای فرانت‌اند و ساخت بیلد پروداکشن
COPY . .
RUN npm run build

# مرحله اجرای نهایی وب‌سرور آسترو با نسخه هماهنگ Node.js 22
FROM node:22-alpine
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./package.json

EXPOSE 3000
ENV HOST=0.0.0.0
ENV PORT=3000

CMD ["node", "./dist/server/entry.mjs"]
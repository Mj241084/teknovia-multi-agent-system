// src/pages/api/share.ts
import type { APIRoute } from 'astro';
import { BASE_URL, isRateLimited } from '../../lib/api';

export const POST: APIRoute = async ({ request }) => {
  try {
    const ip = request.headers.get('x-forwarded-for') || '127.0.0.1';
    const { articleId } = await request.json();

    // مهار نرخ اشتراک گذاری: حداکثر ۳ ثبت در بازه ۵ دقیقه برای هر آی‌پی
    if (await isRateLimited(ip, `share:${articleId}`, 3, 300)) {
      // بازگرداندن پاسخ ۲۰۰ موفقیت‌آمیز فیک جهت اطمینان از نمایش بدون تغییر پیام موفقیت در کلاینت
      return new Response(JSON.stringify({ success: true, rate_limited: true }), { status: 200 });
    }

    const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${articleId}/share/`, {
      method: 'POST'
    });
    const data = await res.json();
    return new Response(JSON.stringify(data), { status: 200 });
  } catch {
    return new Response(JSON.stringify({ error: 'خطای پروکسی اشتراک‌گذاری' }), { status: 500 });
  }
};
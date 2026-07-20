// src/pages/api/view.ts
import type { APIRoute } from 'astro';
import { BASE_URL, isRateLimited } from '../../lib/api';

export const POST: APIRoute = async ({ request }) => {
  try {
    const ip = request.headers.get('x-forwarded-for') || '127.0.0.1';
    const { articleId } = await request.json();

    // مهار نرخ ثبت بازدید: حداکثر ۲ ثبت بازدید در بازه ۵ دقیقه برای هر آی‌پی (بدون تاثیر و پیام در کلاینت)
    if (await isRateLimited(ip, `view:${articleId}`, 2, 300)) {
      return new Response(JSON.stringify({ success: false, message: 'بازدید از قبل ثبت شده است.' }), { status: 200 });
    }

    const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${articleId}/view/`, {
      method: 'POST'
    });
    const data = await res.json();
    return new Response(JSON.stringify(data), { status: 200 });
  } catch {
    return new Response(JSON.stringify({ error: 'خطای پروکسی ثبت بازدید' }), { status: 500 });
  }
};
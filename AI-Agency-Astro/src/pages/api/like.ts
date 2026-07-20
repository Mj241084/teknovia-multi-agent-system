// src/pages/api/like.ts
import type { APIRoute } from 'astro';
import { BASE_URL, isRateLimited } from '../../lib/api';

export const POST: APIRoute = async ({ request }) => {
  try {
    const ip = request.headers.get('x-forwarded-for') || '127.0.0.1';
    const { articleId } = await request.json();

    // مهار سخت‌گیرانه نرخ لایک: حداکثر ۲ پسند در بازه ۵ دقیقه برای هر آی‌پی کاربر
    if (await isRateLimited(ip, `like:${articleId}`, 2, 300)) {
      return new Response(JSON.stringify({ error: 'already_liked' }), { status: 429 });
    }

    const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${articleId}/like/`, {
      method: 'POST'
    });
    const data = await res.json();
    return new Response(JSON.stringify(data), { status: 200 });
  } catch {
    return new Response(JSON.stringify({ error: 'خطای پروکسی پسندیدن' }), { status: 500 });
  }
};
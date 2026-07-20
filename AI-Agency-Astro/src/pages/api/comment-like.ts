// src/pages/api/comment-like.ts
import type { APIRoute } from 'astro';
import { BASE_URL, isRateLimited } from '../../lib/api';

export const POST: APIRoute = async ({ request }) => {
  try {
    const ip = request.headers.get('x-forwarded-for') || '127.0.0.1';
    const { commentId } = await request.json();

    // مهار نرخ لایک کامنت: حداکثر ۵ لایک در دقیقه برای هر آی‌پی کاربر
    if (await isRateLimited(ip, `comment_like:${commentId}`, 5, 60)) {
      return new Response(JSON.stringify({ error: 'تعداد پسند‌های شما بیش از حد مجاز است. لطفاً کمی صبر کنید.' }), { status: 429 });
    }

    const res = await fetch(`${BASE_URL}/api/v1/gateway/comments/${commentId}/like/`, {
      method: 'POST'
    });
    const data = await res.json();
    return new Response(JSON.stringify(data), { status: 200 });
  } catch {
    return new Response(JSON.stringify({ error: 'خطای پروکسی پسندیدن دیدگاه' }), { status: 500 });
  }
};
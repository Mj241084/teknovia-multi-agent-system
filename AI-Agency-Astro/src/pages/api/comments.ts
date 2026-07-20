// src/pages/api/comments.ts
import type { APIRoute } from 'astro';
import { BASE_URL } from '../../lib/api';

export const GET: APIRoute = async ({ request }) => {
  try {
    const url = new URL(request.url);
    const articleId = url.searchParams.get('articleId');
    if (!articleId) {
      return new Response(JSON.stringify({ error: 'شناسه مقاله الزامی است' }), { status: 400 });
    }
    const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${articleId}/comments/`);
    const data = await res.json();
    return new Response(JSON.stringify(data), { status: 200 });
  } catch {
    return new Response(JSON.stringify({ error: 'خطای دریافت کامنت' }), { status: 500 });
  }
};
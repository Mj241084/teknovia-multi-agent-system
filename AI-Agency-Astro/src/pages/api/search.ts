import type { APIRoute } from 'astro';
import { BASE_URL } from '../../lib/api';

export const GET: APIRoute = async ({ request }) => {
  try {
    const url = new URL(request.url);
    const params = url.searchParams.toString();
    const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/search/?${params}`);
    const data = await res.json();
    return new Response(JSON.stringify(data), { status: 200 });
  } catch {
    return new Response(JSON.stringify({ error: 'خطای پروکسی' }), { status: 500 });
  }
};
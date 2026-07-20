import type { APIRoute } from 'astro';

export const POST: APIRoute = async ({ request }) => {
  try {
    const { email } = await request.json();
    // در صورت وجود ای‌پی‌آی خبرنامه در دیتابیس، در اینجا فوروارد می‌شود.
    return new Response(JSON.stringify({ status: 'success', message: 'با موفقیت ثبت شد.' }), { status: 201 });
  } catch {
    return new Response(JSON.stringify({ error: 'خطای پروکسی' }), { status: 500 });
  }
};  
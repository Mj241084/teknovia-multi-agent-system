// src/pages/sitemap.xml.ts
import type { APIRoute } from 'astro';
import { BASE_URL } from '../lib/api';

export const GET: APIRoute = async () => {
  try {
    // ۱. واکشی همزمان دسته‌بندی‌ها و مقالات منتشر شده به صورت مستقیم از وب‌سرویس جنگو
    const [catRes, artRes] = await Promise.all([
      fetch(`${BASE_URL}/api/v1/gateway/categories/`),
      fetch(`${BASE_URL}/api/v1/gateway/articles/search/?page_size=1000`)
    ]);

    const categories = catRes.ok ? await catRes.json() : [];
    const articlesData = artRes.ok ? await artRes.json() : { results: [] };
    const articles = articlesData.results || [];

    const siteUrl = 'https://teknovia.ir'; // با آدرس دامنه نهایی و واقعی خود جایگزین کنید

    // ۲. ساخت خروجی استاندارد نقشه سایت XML
    let sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n`;
    sitemap += `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`;

    // الف) صفحه اصلی سایت
    sitemap += `  <url>\n`;
    sitemap += `    <loc>${siteUrl}/</loc>\n`;
    sitemap += `    <changefreq>daily</changefreq>\n`;
    sitemap += `    <priority>1.0</priority>\n`;
    sitemap += `  </url>\n`;

    // ب) ناوبری داینامیک درخت موضوعی دسته‌بندی‌ها (حذف فیزیکی مواردی که indexable = false هستند از نقشه سایت)
    for (const cat of categories) {
      if (!cat.indexable) continue;

      sitemap += `  <url>\n`;
      sitemap += `    <loc>${siteUrl}/category/${encodeURI(cat.slug)}</loc>\n`;
      sitemap += `    <changefreq>weekly</changefreq>\n`;
      sitemap += `    <priority>0.8</priority>\n`;
      sitemap += `  </url>\n`;
      
      if (cat.children && cat.children.length > 0) {
        for (const child of cat.children) {
          if (!child.indexable) continue;

          sitemap += `  <url>\n`;
          sitemap += `    <loc>${siteUrl}/category/${encodeURI(child.slug)}</loc>\n`;
          sitemap += `    <changefreq>weekly</changefreq>\n`;
          sitemap += `    <priority>0.7</priority>\n`;
          sitemap += `  </url>\n`;
        }
      }
    }

    // ج) ناوبری کل مقالات منتشر شده به ترتیب تاریخ انتشار دقیق دریافتی از دیتابیس
    for (const art of articles) {
      const lastMod = art.publish_date ? new Date(art.publish_date).toISOString() : new Date().toISOString();
      sitemap += `  <url>\n`;
      sitemap += `    <loc>${siteUrl}/post/${encodeURI(art.slug)}</loc>\n`;
      sitemap += `    <lastmod>${lastMod}</lastmod>\n`;
      sitemap += `    <changefreq>monthly</changefreq>\n`;
      sitemap += `    <priority>0.9</priority>\n`;
      sitemap += `  </url>\n`;
    }

    sitemap += `</urlset>`;

    // ۳. بازگرداندن پاسخ با Content-Type مناسب و تنظیم سیستم کش امن ۵ ساعته برای CDNها
    return new Response(sitemap, {
      status: 200,
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Cache-Control': 'public, max-age=3600, s-maxage=18000'
      }
    });

  } catch {
    return new Response('<?xml version="1.0" encoding="UTF-8"?><error>خطا در تولید نقشه داینامیک سایت</error>', {
      status: 500,
      headers: { 'Content-Type': 'application/xml; charset=utf-8' }
    });
  }
};
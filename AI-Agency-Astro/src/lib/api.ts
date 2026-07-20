// src/lib/api.ts
import Redis from 'ioredis';

export const BASE_URL = 'http://127.0.0.1:8001';
// export const BASE_URL = 'https://teknovia.ir';

// پالت رنگ‌های ثابت هشت‌گانه مناسب برای ترکیب ترتیبی دسته‌بندی‌ها
export const DETERMINISTIC_PALETTE = [
  { dot: 'bg-emerald-500', text: 'text-emerald-400', border: 'border-emerald-500/20', bg: 'bg-emerald-500/10' },
  { dot: 'bg-cyan-500', text: 'text-cyan-400', border: 'border-cyan-500/20', bg: 'bg-cyan-500/10' },
  { dot: 'bg-orange-500', text: 'text-orange-400', border: 'border-orange-500/20', bg: 'bg-orange-500/10' },
  { dot: 'bg-rose-500', text: 'text-rose-400', border: 'border-rose-500/20', bg: 'bg-rose-500/10' },
  { dot: 'bg-amber-500', text: 'text-amber-400', border: 'border-emerald-500/20', bg: 'bg-amber-500/10' },
  { dot: 'bg-teal-500', text: 'text-teal-400', border: 'border-teal-500/20', bg: 'bg-teal-500/10' },
  { dot: 'bg-violet-500', text: 'text-violet-400', border: 'border-violet-500/20', bg: 'bg-violet-500/10' },
  { dot: 'bg-fuchsia-500', text: 'text-fuchsia-400', border: 'border-fuchsia-500/20', bg: 'bg-fuchsia-500/10' }
];

export function getCategoryStyle(catId: number): typeof DETERMINISTIC_PALETTE[0] {
  return DETERMINISTIC_PALETTE[catId % DETERMINISTIC_PALETTE.length];
}

// مبدل اعداد به ارقام زیبای فارسی
export function toPersianDigits(num: string | number): string {
  const pAr = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  return num.toString().replace(/[0-9]/g, (w) => pAr[parseInt(w, 10)]);
}

export function formatViewsCount(views: number): string {
  if (views >= 1000000) {
    return toPersianDigits((views / 1000000).toFixed(1)) + ' م';
  }
  if (views >= 1000) {
    return toPersianDigits((views / 1000).toFixed(1)) + ' ه';
  }
  return toPersianDigits(views);
}

export function getRelativePersianTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'هم‌اکنون';
  if (diffMins < 60) return `${toPersianDigits(diffMins)} دقیقه پیش`;
  if (diffHours < 24) return `${toPersianDigits(diffHours)} ساعت پیش`;
  return `${toPersianDigits(diffDays)} روز پیش`;
}

// تابع طلایی تضمین صحت انکودینگ آدرس‌های فارسی حاوی نیم‌فاصله برای جنگو
export function getSafeEncodedParam(param: string): string {
  try {
    return encodeURIComponent(decodeURIComponent(param));
  } catch {
    return encodeURIComponent(param);
  }
}

// اینترفیس‌ها و ساختارهای داده
export interface Article {
  id: number;
  title: string;
  slug: string;
  summary: string;
  content?: string;
  reading_time: number;
  publish_date: string;
  views_count: number;
  likes_count: number;
  share_count: number;
  featured_media: { id: number; media_url: string; alt_text: string } | null;
  categories: { id: number; name: string; slug: string; logo_url?: string; icon_url?: string }[];
  tags: string[];
  short_code: string;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  logo_url?: string;
  icon_url?: string;
  views_count: number;
  children: Category[];
}

// سیستم کش در حافظه رم سرور فرانت‌اند آسترو برای دسته‌بندی‌ها (۲۰ دقیقه کش)
let cachedCategories: Category[] | null = null;
let cacheTimestamp = 0;
const CACHE_TTL = 20 * 60 * 1000;

// سیستم کش اختصاصی و محلی سرور فرانت‌اند برای اخبار فوری (۵ دقیقه کش)
let cachedBreakingNews: any[] | null = null;
let breakingNewsTimestamp = 0;
const BREAKING_NEWS_TTL = 5 * 60 * 1000;

export async function fetchAllCategories(): Promise<Category[]> {
  const now = Date.now();
  if (cachedCategories && (now - cacheTimestamp < CACHE_TTL)) {
    return cachedCategories;
  }
  const res = await fetch(`${BASE_URL}/api/v1/gateway/categories/`);
  if (!res.ok) {
    throw new Error('عدم امکان واکشی لیست دسته‌بندی‌ها از سرور جنگو');
  }
  const data = await res.json();
  cachedCategories = data;
  cacheTimestamp = now;
  return data;
}

export async function fetchBreakingNews(): Promise<any[]> {
  const now = Date.now();
  if (cachedBreakingNews && (now - breakingNewsTimestamp < BREAKING_NEWS_TTL)) {
    return cachedBreakingNews;
  }
  const res = await fetch(`${BASE_URL}/api/v1/gateway/breaking-news/`);
  if (!res.ok) {
    throw new Error('عدم امکان واکشی اخبار فوری از سرور جنگو');
  }
  const data = await res.json();
  cachedBreakingNews = data;
  breakingNewsTimestamp = now;
  return data;
}

export async function fetchHomepageData() {
  const res = await fetch(`${BASE_URL}/api/v1/gateway/homepage/`);
  if (!res.ok) {
    throw new Error('عدم امکان واکشی دیتای صفحه اصلی از سرور جنگو');
  }
  return res.json();
}

export async function fetchCategoryArticles(slug: string, page = 1) {
  const safeSlug = getSafeEncodedParam(slug);
  const res = await fetch(`${BASE_URL}/api/v1/gateway/categories/${safeSlug}/articles/?page=${page}`);
  if (!res.ok) {
    throw new Error(`عدم امکان واکشی مقالات دسته‌بندی با اسلاگ ${slug}`);
  }
  return res.json();
}

export async function fetchArticleDetail(slug: string): Promise<Article> {
  const safeSlug = getSafeEncodedParam(slug);
  const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${safeSlug}/`);
  if (!res.ok) {
    throw new Error(`عدم امکان دریافت جزئیات مقاله با اسلاگ ${slug}`);
  }
  return res.json();
}

export async function resolveShortCode(code: string) {
  const safeCode = getSafeEncodedParam(code);
  const res = await fetch(`${BASE_URL}/api/v1/gateway/s/${safeCode}/`);
  if (!res.ok) {
    throw new Error('کد کوتاه نامعتبر است');
  }
  return res.json();
}

export async function incrementView(id: number) {
  return fetch(`${BASE_URL}/api/v1/gateway/articles/${id}/view/`, { method: 'POST' });
}

export async function likeArticle(id: number) {
  const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${id}/like/`, { method: 'POST' });
  if (!res.ok) throw new Error();
  return res.json();
}

export async function shareArticle(id: number) {
  const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${id}/share/`, { method: 'POST' });
  if (!res.ok) throw new Error();
  return res.json();
}

export async function fetchComments(articleId: number) {
  const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${articleId}/comments/`);
  if (!res.ok) throw new Error();
  return res.json();
}

export async function submitComment(articleId: number, data: { name: string; email?: string; text: string; parent?: number | null }) {
  const res = await fetch(`${BASE_URL}/api/v1/gateway/articles/${articleId}/comments/submit/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error();
  return res.json();
}


// ────────────────────────────────────────────────────────────────
// سیستم کنترلی مهار نرخ درخواست (Rate Limiting) با استفاده از ردیس و فال‌بک رم
// ────────────────────────────────────────────────────────────────

let redis: Redis | null = null;
try {
  redis = new Redis('redis://127.0.0.1:6379', {
    maxRetriesPerRequest: 1,
    connectTimeout: 500,
  });
  redis.on('error', () => {
    // خطا به صورت سایلنت مدیریت می‌شود
  });
} catch {
  redis = null;
}

const memoryLimitMap = new Map<string, { count: number; resetTime: number }>();

export async function isRateLimited(ip: string, action: string, limit: number, windowSeconds: number): Promise<boolean> {
  const key = `teknica_ratelimit:${ip}:${action}`;

  if (redis) {
    try {
      const current = await redis.get(key);
      if (current && parseInt(current, 10) >= limit) {
        return true;
      }
      const pipeline = redis.pipeline();
      pipeline.incr(key);
      if (!current) {
        pipeline.expire(key, windowSeconds);
      }
      await pipeline.exec();
      return false;
    } catch {
      // در صورت بروز هرگونه خطای ارتباطی در ردیس، به Fallback حافظه رم سیستم سوئیچ می‌شود
    }
  }

  const now = Date.now();
  const record = memoryLimitMap.get(key);

  if (record && now < record.resetTime) {
    if (record.count >= limit) {
      return true;
    }
    record.count++;
    return false;
  }

  memoryLimitMap.set(key, {
    count: 1,
    resetTime: now + (windowSeconds * 1000)
  });
  return false;
}
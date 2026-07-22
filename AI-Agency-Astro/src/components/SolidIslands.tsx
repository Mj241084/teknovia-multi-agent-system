// src/components/SolidIslands.tsx
import { createSignal, createEffect, For, Show, onMount } from 'solid-js';
import { Portal } from 'solid-js/web';
import { 
  SunIcon, MoonIcon, SearchIcon, ChevronLeft, ChevronRight, 
  LikeIcon, ShareIcon, CommentIcon, ViewsIcon, ClockIcon, SendIcon, SparklesIcon, WinkIcon
} from './Icons';

export const [isSearchOpen, setIsSearchOpen] = createSignal(false);
const [toast, setToSignal] = createSignal<{ message: string; type: 'success' | 'error' | 'heart' } | null>(null);

// ۱. تابع کمکی مبدل اعداد انگلیسی به ارقام زیبای فارسی
export function toPersian(num: number | string): string {
  const pAr = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  return num.toString().replace(/[0-9]/g, (w) => pAr[parseInt(w, 10)]);
}

// ۲. مبدل زمان نسبی فارسی سراسری
export function getRelativePersianTimeJS(dateStr: string): string {
  if (!dateStr) return 'هم‌اکنون';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'هم‌اکنون';
  if (diffMins < 60) return `${toPersian(diffMins)} دقیقه پیش`;
  if (diffHours < 24) return `${toPersian(diffHours)} ساعت پیش`;
  return `${toPersian(diffDays)} روز پیش`;
}

export function showToast(message: string, type: 'success' | 'error' | 'heart' = 'success') {
  setToSignal({ message, type });
  setTimeout(() => setToSignal(null), 4000);
}

// ۳. تاگل تم روشن/تیره
export function ThemeToggle() {
  const [theme, setTheme] = createSignal<'dark' | 'light'>('dark');

  onMount(() => {
    const saved = localStorage.getItem('theme') || 'dark';
    setTheme(saved as 'dark' | 'light');
  });

  const toggle = () => {
    const next = theme() === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem('theme', next);
    document.documentElement.classList.add('disable-transitions');
    document.documentElement.classList.toggle('light', next === 'light');
    setTimeout(() => {
      document.documentElement.classList.remove('disable-transitions');
    }, 20);
  };

  return (
    <button onClick={toggle} aria-label="تغییر تم" class="h-9 w-9 rounded-full flex items-center justify-center bg-muted/60 hover:bg-muted border border-border/40 transition">
      <Show when={theme() === 'dark'} fallback={<SunIcon class="h-4 w-4 text-foreground" />}>
        <MoonIcon class="h-4 w-4 text-foreground" />
      </Show>
    </button>
  );
}

// ۴. تیکر اخبار فوری چسبان
export function LiveTicker(props: { news: any[] }) {
  return (
    <div class="flex items-center border-b border-border/50 bg-background h-10 overflow-hidden relative dir-rtl">
      <div class="bg-rose-600 text-white px-4 h-full flex items-center gap-2 text-xs font-bold z-10 shadow-lg shrink-0">
        <span class="w-2 h-2 rounded-full bg-white animate-pulse"></span>
        <span>اخبار فوری</span>
      </div>
      <div class="flex-1 overflow-x-auto scrollbar-none flex items-center px-4 gap-6 select-none">
        <For each={props.news}>
          {(item) => (
            <a href={`/post/${encodeURI(item.slug)}`} class="text-xs text-foreground/85 hover:text-emerald-400 transition flex items-center gap-2 shrink-0">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              {item.title}
            </a>
          )}
        </For>
      </div>
    </div>
  );
}

// ۵. ذره‌بین هدر جهت لود اورلی
export function SearchTrigger() {
  return (
    <button onClick={() => setIsSearchOpen(true)} aria-label="جستجو" class="h-9 w-9 rounded-full flex items-center justify-center bg-muted/60 hover:bg-muted border border-border/40 transition">
      <SearchIcon class="h-4 w-4 text-foreground" />
    </button>
  );
}

// ۶. اورلی شیشه‌ای و بلوری جستجو
export function SearchOverlay() {
  let inputRef: HTMLInputElement | undefined;

  createEffect(() => {
    if (isSearchOpen()) {
      setTimeout(() => inputRef?.focus(), 100);
    }
  });

  const handleSearch = (e: Event) => {
    e.preventDefault();
    if (inputRef && inputRef.value.trim()) {
      const q = inputRef.value.trim();
      setIsSearchOpen(false);
      window.location.href = `/search?q=${encodeURIComponent(q)}`;
    }
  };

  return (
    <Show when={isSearchOpen()}>
      <div class="fixed inset-0 z-50 backdrop-blur-xl bg-black/60 flex items-center justify-center p-6 animate-fade-in">
        <button onClick={() => setIsSearchOpen(false)} class="absolute top-6 left-6 text-white text-lg">✕</button>
        <form onSubmit={handleSearch} class="w-full max-w-xl flex items-center gap-3 border-b-2 border-emerald-500 pb-2">
          <input 
            ref={inputRef}
            type="text" 
            placeholder="عبارت مورد نظر خود را بنویسید و اینتر بزنید..." 
            class="flex-1 bg-transparent text-white text-lg focus:outline-none placeholder-white/50 text-right dir-rtl"
          />
          <button type="submit" class="text-emerald-400">
            <SearchIcon class="h-6 w-6" />
          </button>
        </form>
      </div>
    </Show>
  );
}

// ۷. کامپوننت یکپارچه هیرو اسلایدر با رندر کاملاً پویا دسته‌بندی‌ها و ویدیو
export function HeroSliderSection(props: { articles: any[] }) {
  const [active, setActive] = createSignal(0);
  const totalSlides = () => Math.min(props.articles.length, 3);

  const handleNext = () => {
    setActive((prev) => (prev + 1) % totalSlides());
  };

  const handlePrev = () => {
    setActive((prev) => (prev - 1 + totalSlides()) % totalSlides());
  };

  const sideIndices = () => {
    const indices: number[] = [];
    for (let i = 0; i < totalSlides(); i++) {
      if (i !== active()) {
        indices.push(i);
      }
    }
    return indices;
  };

  return (
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 text-right dir-rtl w-full">
      <div class="lg:col-span-2 relative h-96 w-full rounded-2xl overflow-hidden group shadow-xl">
        <For each={props.articles.slice(0, 3)}>
          {(item, i) => {
            const category = item.categories?.[0] || { id: 1, name: 'هوش مصنوعی', slug: 'ai' };
            return (
              <div class={`absolute inset-0 transition-opacity duration-750 ${active() === i() ? 'opacity-100 z-10' : 'opacity-0 z-0'}`}>
                <a href={`/post/${encodeURI(item.slug)}`} class="block w-full h-full relative">
                  <Show when={item.featured_media?.media_type === 'video'} fallback={
                    <img 
                      src={item.featured_media?.media_url || 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80'} 
                      alt={item.title} 
                      class="w-full h-full object-cover" 
                      loading={i() === 0 ? "eager" : "lazy"} 
                      fetchpriority={i() === 0 ? "high" : "low"} 
                      decoding="async"
                    />
                  }>
                    <video 
                      src={item.featured_media.media_url} 
                      class="w-full h-full object-cover" 
                      autoplay 
                      loop 
                      muted 
                      playsinline
                    />
                  </Show>
                  <div class="absolute inset-0 bg-gradient-to-t from-black/95 via-black/45 to-transparent"></div>
                  <div class="absolute bottom-0 right-0 left-0 p-6 space-y-3 z-20">
                    <span class="bg-emerald-500 text-white text-[10px] px-2.5 py-0.5 rounded-full font-bold w-fit inline-block">
                      {category.name}
                    </span>
                    <h2 class="text-xl sm:text-2xl font-black text-white hover:text-emerald-400 transition-colors">{item.title}</h2>
                    <p class="text-xs text-white/80 line-clamp-2">{item.summary}</p>
                  </div>
                </a>
              </div>
            );
          }}
        </For>

        <div class="absolute inset-y-0 left-4 flex items-center z-30 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={(e) => { e.stopPropagation(); handlePrev(); }} aria-label="اسلاید قبلی" class="h-8 w-8 rounded-full bg-black/60 hover:bg-emerald-500 text-white flex items-center justify-center transition">
            <ChevronLeft class="h-4 w-4" />
          </button>
        </div>
        <div class="absolute inset-y-0 right-4 flex items-center z-30 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={(e) => { e.stopPropagation(); handleNext(); }} aria-label="اسلاید بعدی" class="h-8 w-8 rounded-full bg-black/60 hover:bg-emerald-500 text-white flex items-center justify-center transition">
            <ChevronRight class="h-4 w-4" />
          </button>
        </div>
      </div>

      <div class="lg:col-span-1 flex flex-col gap-4">
        <For each={sideIndices()}>
          {(idx) => {
            const item = props.articles[idx];
            const category = item.categories?.[0] || { id: 1, name: 'فناوری', slug: 'tech' };
            return (
              <a 
                href={`/post/${encodeURI(item.slug)}`}
                class="relative h-[180px] rounded-2xl overflow-hidden group cursor-pointer border border-transparent hover:border-emerald-500/50 hover:shadow-lg transition-all duration-300 block"
              >
                <Show when={item.featured_media?.media_type === 'video'} fallback={
                  <img 
                    src={item.featured_media?.media_url || 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80'} 
                    alt={item.title} 
                    class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" 
                    loading="lazy" 
                    decoding="async"
                  />
                }>
                  <video 
                    src={item.featured_media.media_url} 
                    class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" 
                    autoplay 
                    loop 
                    muted 
                    playsinline
                  />
                </Show>
                <div class="absolute inset-0 bg-gradient-to-t from-black/95 via-black/45 to-transparent"></div>
                <div class="absolute bottom-0 right-0 left-0 p-4 space-y-1 z-20">
                  <span class="bg-cyan-500 text-white text-[9px] px-2 py-0.5 rounded-full font-bold w-fit inline-block">
                    {category.name}
                  </span>
                  <h3 class="text-sm font-bold text-white line-clamp-2 group-hover:text-emerald-400 transition-colors">
                    {item.title}
                  </h3>
                </div>
              </a>
            );
          }}
        </For>
      </div>
    </div>
  );
}

// ۸. منوی همبرگری موبایل
export function MobileMenu(props: { children: any }) {
  const [isOpen, setIsOpen] = createSignal(false);
  return (
    <>
      <button onClick={() => setIsOpen(true)} aria-label="منوی ناوبری موبایل" class="lg:hidden h-9 w-9 flex items-center justify-center bg-muted/60 rounded-full border border-border/40">
        <svg class="h-5 w-5 text-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" /></svg>
      </button>
      <Portal>
        <div class={`fixed inset-0 z-50 flex justify-start bg-black/60 backdrop-blur-sm transition-opacity duration-200 text-right dir-rtl ${isOpen() ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}>
          <div class={`w-[280px] bg-card border-l border-border/60 h-full p-6 flex flex-col space-y-6 overflow-y-auto transition-transform duration-200 ${isOpen() ? 'translate-x-0' : 'translate-x-full'}`}>
            <div class="flex items-center justify-between border-b border-border/50 pb-3">
              <span class="font-black text-emerald-400">تکنوویا</span>
              <button onClick={() => setIsOpen(false)} class="text-foreground">✕</button>
            </div>
            <div class="flex-1 text-right dir-rtl">
              {props.children}
            </div>
          </div>
        </div>
      </Portal>
    </>
  );
}

// ۹. بخش تعاملی خبرنامه
export function NewsletterSection() {
  const [email, setEmail] = createSignal('');
  const [success, setSuccess] = createSignal(false);
  const [loading, setLoading] = createSignal(false);

  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    if (!email().includes('@')) {
      showToast('لطفاً یک ایمیل معتبر وارد کنید', 'error');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email() })
      });
      if (res.ok) {
        setSuccess(true);
        showToast('عضویت شما در خبرنامه ثبت شد');
      }
    } catch {
      showToast('خطا در برقراری ارتباط با سرور', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div class="relative overflow-hidden rounded-3xl border border-emerald-500/15 bg-gradient-to-br from-emerald-950/20 to-teal-950/20 p-8 md:p-12">
      <div class="absolute -top-12 -right-12 w-48 h-48 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none"></div>
      <div class="absolute -bottom-12 -left-12 w-48 h-48 bg-teal-500/5 rounded-full blur-3xl pointer-events-none"></div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center text-right dir-rtl">
        <div class="space-y-3">
          <span class="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full text-[11px] px-3 py-1 font-bold w-fit flex items-center gap-1.5">
            <SparklesIcon class="h-3.5 w-3.5 text-emerald-400" />
            <span>خبرنامه هفتگی تکنوویا</span>
          </span>
          <h3 class="text-xl sm:text-2xl font-black">مهم‌ترین اخبار هوش مصنوعی و فناوری را <span class="text-emerald-400">هر شنبه صبح</span> در ایمیلتان بگیرید</h3>
          <p class="text-xs text-muted-foreground leading-relaxed">به بیش از ۴۸,۰۰۰ مشترک بپیوندید و از تحلیل‌های اختصاصی، گزارش‌های عمیق و انتخاب‌های سردبیر مطلع شوید. بدون اسپم، هر زمان خواستید لغو عضویت.</p>
        </div>
        <div class="flex flex-col gap-2">
          <Show when={!success()} fallback={
            <div class="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-xl p-4 text-center font-bold text-sm">
              ✓ عضویت شما با موفقیت ثبت شد و هر شنبه برای شما ارسال خواهد شد.
            </div>
          }>
            <form onSubmit={handleSubmit} class="flex flex-col sm:flex-row-reverse gap-3">
              <div class="flex-1 relative flex items-center bg-muted/40 border border-border/50 rounded-xl px-4 py-2.5">
                <input 
                  type="email" 
                  placeholder="ایمیل شما" 
                  value={email()}
                  onInput={(e) => setEmail(e.currentTarget.value)}
                  class="w-full bg-transparent text-sm focus:outline-none placeholder-muted-foreground text-right"
                  required
                />
              </div>
              <button type="submit" disabled={loading()} class="bg-gradient-to-r from-emerald-500 to-teal-600 shadow-lg shadow-emerald-500/15 text-white font-bold text-xs h-11 px-6 rounded-xl flex items-center justify-center gap-2 cursor-pointer hover:from-emerald-600 hover:to-teal-700 transition">
                <span>عضویت</span>
                <SendIcon class="h-3.5 w-3.5" />
              </button>
            </form>
          </Show>
          <p class="text-[10px] text-muted-foreground/70">با عضویت، با <a href="/privacy" class="underline">قوانین حریم خصوصی</a> ما موافقت می‌کنیم.</p>
        </div>
      </div>
    </div>
  );
}

// ۱۰. پنل پیشرفته جستجوی داینامیک
export function AdvancedSearchPanel(props: { initialQuery?: string; initialCategory?: string; initialTag?: string; categories: any[] }) {
  const [query, setQuery] = createSignal(props.initialQuery || '');
  const [category, setCategory] = createSignal(props.initialCategory || '');
  const [tag, setTag] = createSignal(props.initialTag || '');
  const [timeRange, setTimeRange] = createSignal('');
  const [sortBy, setSortBy] = createSignal('latest');
  const [results, setResults] = createSignal<any[]>([]);
  const [loading, setLoading] = createSignal(false);

  const fetchResults = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (query()) params.append('q', query());
      if (category()) params.append('category', category());
      if (tag()) params.append('tag', tag());
      if (timeRange()) params.append('time_range', timeRange());
      if (sortBy()) params.append('sort_by', sortBy());

      const newUrl = `/search?${params.toString()}`;
      window.history.pushState(null, '', newUrl);

      const res = await fetch(`/api/search?${params.toString()}`);
      const data = await res.json();
      setResults(data.results || []);
    } catch {
      showToast('خطا در بارگذاری نتایج', 'error');
    } finally {
      setLoading(false);
    }
  };

  onMount(() => {
    fetchResults();
  });

  const handleFormSearch = (e: Event) => {
    e.preventDefault();
    setTag('');
    fetchResults();
  };

  return (
    <div class="space-y-8 text-right dir-rtl">
      <form onSubmit={handleFormSearch} class="bg-card border border-border/50 p-6 rounded-2xl gap-4 flex flex-col sm:flex-row items-center justify-between">
        <div class="flex-1 w-full relative flex items-center bg-muted/30 border border-border/60 rounded-xl px-4 py-2.5">
          <input 
            type="text" 
            placeholder="جستجو ..." 
            value={query()}
            onInput={(e) => setQuery(e.currentTarget.value)}
            class="w-full bg-transparent text-sm focus:outline-none placeholder-muted-foreground text-right"
          />
        </div>
        <button type="submit" class="w-full sm:w-auto bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs h-11 px-6 rounded-xl transition">
          اعمال فیلتر
        </button>
      </form>

      <Show when={tag()}>
        <div class="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-3 py-1.5 rounded-xl text-xs w-fit">
          <span>درحال نمایش مقالات برچسب: #{tag()}</span>
          <button type="button" onClick={() => { setTag(''); fetchResults(); }} class="text-rose-500 hover:text-rose-400 font-bold mr-1 cursor-pointer" aria-label="حذف برچسب">✕</button>
        </div>
      </Show>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <select value={category()} onChange={(e) => { setCategory(e.currentTarget.value); fetchResults(); }} class="bg-card border border-border/60 p-3 rounded-xl text-xs focus:outline-none">
          <option value="">همه دسته‌بندی‌ها</option>
          <For each={props.categories}>
            {(cat) => (
              <option value={cat.slug}>{cat.name}</option>
            )}
          </For>
        </select>
        <select value={timeRange()} onChange={(e) => { setTimeRange(e.currentTarget.value); fetchResults(); }} class="bg-card border border-border/60 p-3 rounded-xl text-xs focus:outline-none">
          <option value="">هر زمان</option>
          <option value="day">۲۴ ساعت گذشته</option>
          <option value="week">هفته گذشته</option>
          <option value="month">ماه گذشته</option>
        </select>
        <select value={sortBy()} onChange={(e) => { setSortBy(e.currentTarget.value); fetchResults(); }} class="bg-card border border-border/60 p-3 rounded-xl text-xs focus:outline-none">
          <option value="latest">آخرین اخبار</option>
          <option value="popular">پربازدیدترین‌ها</option>
          <option value="likes">محبوب‌ترین‌ها (لایک)</option>
        </select>
      </div>

      <div class="relative">
        <Show when={loading()}>
          <div class="absolute inset-0 bg-background/50 flex items-center justify-center z-10 py-12">
            <span class="w-8 h-8 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin"></span>
          </div>
        </Show>

        <Show when={results().length > 0} fallback={
          <div class="text-center py-12 text-muted-foreground text-sm border border-dashed border-border rounded-xl">
            هیچ نتیجه‌ای یافت نشد. فیلترها را تغییر دهید.
          </div>
        }>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <For each={results()}>
              {(item) => (
                <article class="bg-card/50 border border-border/50 rounded-xl overflow-hidden flex flex-col p-4 space-y-3">
                  <a href={`/post/${encodeURI(item.slug)}`} class="block h-40 w-full overflow-hidden rounded-lg">
                    <img 
                      src={item.featured_media?.media_url || 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80'} 
                      alt={item.title} 
                      class="w-full h-full object-cover hover:scale-105 transition-transform duration-700" 
                      loading="lazy" 
                      decoding="async"
                    />
                  </a>
                  
                  <div class="space-y-2 flex-1 flex flex-col justify-between">
                    <div class="space-y-1">
                      <h3 class="font-bold text-sm line-clamp-1 hover:text-emerald-400 transition-colors">
                        <a href={`/post/${encodeURI(item.slug)}`}>{item.title}</a>
                      </h3>
                      <p class="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                        <a href={`/post/${encodeURI(item.slug)}`} class="hover:text-foreground/90 transition-colors">{item.summary}</a>
                      </p>
                    </div>

                    <Show when={item.tags && item.tags.length > 0}>
                      <div class="flex flex-wrap gap-1 pt-1.5">
                        <For each={item.tags}>
                          {(t) => (
                            <span 
                              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setTag(t); fetchResults(); }} 
                              class="text-[9.5px] text-muted-foreground hover:text-emerald-400 bg-muted/40 px-2 py-0.5 rounded border border-border/30 transition cursor-pointer"
                            >
                              #{t}
                            </span>
                          )}
                        </For>
                      </div>
                    </Show>
                    
                    <div class="flex justify-between items-center text-[10px] text-muted-foreground border-t border-border/30 pt-2 mt-2">
                      <span>{toPersian(item.reading_time)} دقیقه مطالعه</span>
                      <span class="text-muted-foreground/60">{getRelativePersianTimeJS(item.publish_date)}</span>
                    </div>
                  </div>
                </article>
              )}
            </For>
          </div>
        </Show>
      </div>
    </div>
  );
}

// ۱۱. ماژول تعاملات با مهار لیمیت
export function ArticleHeaderInteractions(props: { 
  articleId: number; 
  likesCount: number; 
  slug: string; 
  shortCode: string;
  publishDate: string;
  viewsCount: number;
  readingTime: number;
}) {
  const [likes, setLikes] = createSignal(props.likesCount);
  const [isSticky, setIsSticky] = createSignal(false);
  let staticContainerRef: HTMLDivElement | undefined;

  onMount(async () => {
    try {
      await fetch('/api/view', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ articleId: props.articleId })
      });
    } catch (e) {
      // مهار سایلنت خطاها
    }

    const observer = new IntersectionObserver(([entry]) => {
      setIsSticky(!entry.isIntersecting);
    }, { threshold: 0 });

    if (staticContainerRef) {
      observer.observe(staticContainerRef);
    }
  });

  const getRelativeTime = () => {
    return getRelativePersianTimeJS(props.publishDate);
  };

  const handleLike = async () => {
    try {
      const res = await fetch('/api/like', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ articleId: props.articleId })
      });
      if (res.ok) {
        const data = await res.json();
        setLikes(data.likes_count);
        showToast('دمت گرم ', 'heart'); 
      } else if (res.status === 429) {
        showToast('قبلا لایک کردی', 'error'); 
      }
    } catch {
      showToast('خطا در ثبت پسند دیدگاه', 'error');
    }
  };

  const handleShare = async () => {
    try {
      const res = await fetch('/api/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ articleId: props.articleId })
      });
      
      const shortUrl = `${window.location.origin}/s/${props.shortCode}`;
      await navigator.clipboard.writeText(shortUrl);
      showToast('لینک کپی شد', 'success');
    } catch {
      showToast('خطا در کپی لینک', 'error');
    }
  };

  return (
    <>
      <div ref={staticContainerRef} class="flex flex-row items-center justify-between text-xs text-muted-foreground border-b border-border/40 pb-4">
        
        <div class="flex items-center gap-2">
          <button onClick={handleLike} class="flex items-center gap-1 px-3 h-8 rounded-full border border-border/50 bg-card/50 hover:bg-muted text-[11px] font-bold transition">
            <LikeIcon class="h-3.5 w-3.5 text-rose-500" />
            <span class="text-rose-500 font-sans">{toPersian(likes())}</span>
          </button>
          <button onClick={handleShare} class="flex items-center justify-center w-8 h-8 rounded-full border border-border/50 bg-card/50 hover:bg-muted transition" aria-label="اشتراک‌گذاری">
            <ShareIcon class="h-3.5 w-3.5 text-emerald-400" />
          </button>
        </div>

        <div class="flex items-center gap-2 font-medium">
          <span class="font-sans">{getRelativeTime()}</span>
          <span>•</span>
          <span class="flex items-center gap-1">
            <ViewsIcon class="h-3.5 w-3.5" />
            <span class="font-sans">{toPersian(props.viewsCount)}</span>
          </span>
          <span>•</span>
          <span class="flex items-center gap-1">
            <ClockIcon class="h-3.5 w-3.5" />
            <span class="font-sans">{toPersian(props.readingTime)} دقیقه مطالعه</span>
          </span>
        </div>

      </div>

      <Show when={isSticky()}>
        <Portal>
          <div class="fixed bottom-0 left-0 right-0 sm:bottom-4 sm:left-4 sm:right-4 max-w-3xl mx-auto bg-card/90 backdrop-blur-md border border-border/60 py-3 px-6 z-40 flex items-center justify-between shadow-2xl rounded-t-2xl sm:rounded-2xl animate-fade-in text-xs text-muted-foreground dir-rtl">
            <div class="flex items-center gap-2">
              <button onClick={handleLike} class="flex items-center gap-1 px-3 h-8 rounded-full border border-border/50 bg-background/50 hover:bg-muted text-[11px] font-bold transition">
                <LikeIcon class="h-3.5 w-3.5 text-rose-500" />
                <span class="text-rose-500 font-sans">{toPersian(likes())}</span>
              </button>
              <button onClick={handleShare} class="flex items-center justify-center w-8 h-8 rounded-full border border-border/50 bg-background/50 hover:bg-muted transition" aria-label="اشتراک‌گذاری">
                <ShareIcon class="h-3.5 w-3.5 text-emerald-400" />
              </button>
            </div>
            
            <div class="flex items-center gap-2 font-medium">
              <span class="flex items-center gap-1">
                <ViewsIcon class="h-3.5 w-3.5" />
                <span class="font-sans">{toPersian(props.viewsCount)}</span>
              </span>
              <span>•</span>
              <span class="flex items-center gap-1">
                <ClockIcon class="h-3.5 w-3.5" />
                <span class="font-sans">{toPersian(props.readingTime)} دقیقه</span>
              </span>
            </div>
          </div>
        </Portal>
      </Show>
    </>
  );
}

// ۱۲. جزیره تعاملی مقالات مشابه
export function SimilarArticles(props: { articles: any[] }) {
  return (
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <For each={props.articles}>
        {(sim) => (
          <a href={`/post/${encodeURI(sim.slug)}`} class="flex items-center gap-3 bg-card/45 border border-border/50 rounded-xl p-3 hover:border-emerald-500/50 hover:shadow-lg transition">
            <div class="w-16 h-16 rounded-lg overflow-hidden shrink-0">
              <img 
                src={sim.featured_media_url || 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=150&q=80'} 
                alt="" 
                class="w-full h-full object-cover" 
                loading="lazy" 
                decoding="async" 
              />
            </div>
            <div class="flex-1 min-w-0">
              <h4 class="text-xs font-bold line-clamp-2 text-foreground/90 hover:text-emerald-400 transition-colors">{sim.title}</h4>
              <p class="text-[10px] text-muted-foreground mt-1 line-clamp-1">{sim.summary}</p>
            </div>
          </a>
        )}
      </For>
    </div>
  );
}

// ۱۳. کامپوننت نود بازگشتی درخت دیدگاه‌ها
export function CommentNode(props: { 
  comment: any; 
  onReply: (id: number) => void; 
  onLike: (id: number) => void; 
  isReply?: boolean;
}) {
  return (
    <div class={`${props.isReply ? 'mr-6 mt-2 border-r-2 border-emerald-500 bg-muted/40' : 'border border-border/40 bg-muted/20'} p-3 rounded-xl space-y-2 text-right dir-rtl`}>
      <div class="flex justify-between items-center text-[10px]">
        <div class="flex items-center gap-1.5">
          <span class="block font-bold text-foreground leading-normal font-sans">{props.comment.name}</span>
          <span class="text-muted-foreground/60 leading-normal">•</span>
          <span class="text-muted-foreground font-sans text-[9px] leading-normal">{getRelativePersianTimeJS(props.comment.created_at)}</span>
        </div>
        
        <button onClick={() => props.onLike(props.comment.id)} class="flex items-center gap-1 px-2.5 py-0.5 rounded-full border border-border/50 bg-background/50 hover:bg-muted text-[9px] font-bold transition group">
          <LikeIcon class="h-3 w-3 text-rose-500 group-hover:scale-110 transition-transform" />
          <span class="text-rose-500 font-sans">{toPersian(props.comment.likes_count || 0)}</span>
        </button>
      </div>
      
      <p class="text-xs text-foreground/90 leading-relaxed font-sans">{props.comment.text}</p>
      
      <div class="flex gap-4">
        <button onClick={() => props.onReply(props.comment.id)} class="text-[10px] text-emerald-400 hover:underline">
          پاسخ به این نظر
        </button>
      </div>

      <Show when={props.comment.replies && props.comment.replies.length > 0}>
        <div class="space-y-2 mt-2">
          <For each={props.comment.replies}>
            {(reply) => (
              <CommentNode comment={reply} onReply={props.onReply} onLike={props.onLike} isReply={true} />
            )}
          </For>
        </div>
      </Show>
    </div>
  );
}

// ۱۴. ماژول نظرات
export function ArticleComments(props: { articleId: number }) {
  const [comments, setComments] = createSignal<any[]>([]);
  const [name, setName] = createSignal('');
  const [email, setEmail] = createSignal('');
  const [text, setText] = createSignal('');
  const [parent, setParent] = createSignal<number | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [visibleCount, setVisibleCount] = createSignal(5);

  onMount(async () => {
    try {
      const res = await fetch(`/api/comments?articleId=${props.articleId}`);
      if (res.ok) {
        const data = await res.json();
        setComments(data);
      }
    } catch {
      // مهار خطاها
    }
  });

  const handleCommentSubmit = async (e: Event) => {
    e.preventDefault();
    if (text().trim().length < 5) {
      showToast('متن نظر باید حداقل ۵ کاراکتر باشد', 'error');
      return;
    }
    if (name().length > 30 || text().length > 500) {
      showToast('خطا در محدودیت کاراکتر فیلدها', 'error');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/comment-submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          articleId: props.articleId,
          name: name(),
          email: email(),
          text: text(),
          parent: parent()
        })
      });
      if (res.ok) {
        showToast('دیدگاه شما با موفقیت ثبت شد و پس از بررسی و تایید ناظران منتشر خواهد شد.', 'success');
        setText('');
        setName('');
        setEmail('');
        setParent(null);
      } else if (res.status === 429) {
        showToast('به سقف کامنت برای این مقاله رسیده', 'error'); 
      } else {
        showToast('خطا در ارسال دیدگاه', 'error');
      }
    } catch {
      showToast('خطای شبکه', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCommentLike = async (commentId: number) => {
    try {
      const res = await fetch('/api/comment-like', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ commentId })
      });
      if (res.ok) {
        const data = await res.json();
        
        const updateLikesRecursive = (list: any[]): any[] => {
          return list.map(c => {
            if (c.id === commentId) {
              return { ...c, likes_count: data.likes_count };
            }
            if (c.replies && c.replies.length > 0) {
              return { ...c, replies: updateLikesRecursive(c.replies) };
            }
            return c;
          });
        };

        setComments(prev => updateLikesRecursive(prev));
        showToast('دیدگاه پسند شد');
      } else if (res.status === 429) {
        showToast('آرام‌تر! چند لحظه دیگر دوباره تلاش کنید', 'error');
      }
    } catch {
      showToast('خطا در ثبت پسند دیدگاه', 'error');
    }
  };

  const isSubmitDisabled = () => {
    const nameLen = name().trim().length;
    const textLen = text().trim().length;
    return nameLen === 0 || textLen === 0 || name().length > 30 || text().length > 500 || loading();
  };

  return (
    <div class="space-y-6 text-right dir-rtl">
      <h3 class="font-black text-sm text-foreground">ارسال دیدگاه</h3>
      <form onSubmit={handleCommentSubmit} class="space-y-3">
        <Show when={parent()}>
          <div class="p-2 bg-muted/40 rounded border border-border flex justify-between text-[11px]">
            <span>پاسخ به دیدگاه شناسه {parent()}</span>
            <button type="button" onClick={() => setParent(null)} class="text-rose-500">انصراف</button>
          </div>
        </Show>
        
        <div class="grid grid-cols-2 gap-3">
          <div class="relative flex items-center w-full">
            <input 
              type="text" 
              placeholder="نام شما" 
              value={name()}
              onInput={(e) => setName(e.currentTarget.value)}
              required
              class="w-full pl-12 pr-3 py-2 text-xs bg-muted/40 border border-border/50 rounded-lg focus:outline-none focus:border-emerald-500 text-foreground font-sans text-right"
            />
            <span class={`absolute left-3 text-[10px] font-sans transition-colors ${name().length > 30 ? 'text-rose-500 font-bold' : 'text-muted-foreground/60'}`}>
              {toPersian(name().length)}/{toPersian(30)}
            </span>
          </div>
          
          <input 
            type="email" 
            placeholder="ایمیل (اختیاری)" 
            value={email()}
            onInput={(e) => setEmail(e.currentTarget.value)}
            class="px-3 py-2 text-xs bg-muted/40 border border-border/50 rounded-lg focus:outline-none focus:border-emerald-500 text-foreground font-sans text-right"
          />
        </div>

        <div class="relative flex flex-col justify-end w-full">
          <textarea 
            placeholder="دیدگاه خود را وارد کنید..." 
            rows="3"
            value={text()}
            onInput={(e) => setText(e.currentTarget.value)}
            required
            class="w-full pl-14 pr-3 py-2 text-xs bg-muted/40 border border-border/50 rounded-lg focus:outline-none focus:border-emerald-500 text-foreground font-sans"
          />
          <span class={`absolute left-3 bottom-3 text-[10px] font-sans transition-colors ${text().length > 500 ? 'text-rose-500 font-bold' : 'text-muted-foreground/60'}`}>
            {toPersian(text().length)}/{toPersian(500)}
          </span>
        </div>

        <button 
          type="submit" 
          disabled={isSubmitDisabled()} 
          class={`text-[11px] font-bold px-4 py-2 rounded-lg transition flex items-center gap-1 ${
            isSubmitDisabled() 
              ? 'bg-muted/40 text-muted-foreground/50 cursor-not-allowed border border-border/30' 
              : 'bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer'
          }`}
        >
          <span>ارسال دیدگاه</span>
          <SendIcon class="h-3 w-3" />
        </button>
      </form>

      <div class="space-y-4">
        <Show when={comments().length === 0}>
          <div class="p-4 text-center border border-dashed border-emerald-500/30 rounded-xl bg-emerald-500/5 flex flex-col items-center justify-center space-y-1.5 max-w-sm mx-auto animate-fade-in">
            <WinkIcon class="h-6 w-6 text-emerald-400 animate-pulse" />
            <p class="text-xs font-bold text-foreground">هنوز هیچ دیدگاهی برای این مطلب ثبت نشده است.</p>
            <p class="text-[9.5px] text-muted-foreground leading-normal">نخستین دیدگاه را شما بنویسید! اولین نفر باشید و نظرتان را ثبت کنید.</p>
          </div>
        </Show>

        <For each={comments().slice(0, visibleCount())}>
          {(comment) => (
            <CommentNode 
              comment={comment} 
              onReply={setParent} 
              onLike={handleCommentLike} 
            />
          )}
        </For>

        <Show when={comments().length > visibleCount()}>
          <div class="flex justify-end pt-2">
            <button 
              onClick={() => setVisibleCount(prev => prev + 5)} 
              class="text-[9.5px] font-bold text-emerald-400 hover:text-emerald-300 bg-muted/40 px-3 py-1.5 rounded-lg border border-border/30 hover:border-emerald-500/30 transition-all cursor-pointer"
            >
              نمایش دیدگاه‌های بیشتر...
            </button>
          </div>
        </Show>

      </div>
    </div>
  );
}

// ۱۵. ماژول توست کلاینتی
export function ToastContainer() {
  return (
    <Show when={toast()}>
      <div class="fixed top-6 left-1/2 -translate-x-1/2 z-50 p-3 rounded-xl border border-emerald-500/30 bg-card/90 backdrop-blur text-xs font-bold transition animate-bounce flex items-center gap-2">
        <Show when={toast()?.type === 'success'}>
          <span class="text-emerald-400">●</span>
        </Show>
        <Show when={toast()?.type === 'error'}>
          <span class="text-rose-500">●</span>
        </Show>
        <Show when={toast()?.type === 'heart'}>
          <LikeIcon class="h-4 w-4 text-rose-500 animate-pulse" />
        </Show>
        <span>{toast()?.message}</span>
      </div>
    </Show>
  );
}
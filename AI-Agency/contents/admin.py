from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Category, MediaContainer, Content, PostsContainer, Tag


# ────────────────────────────────────────────────────────────────
# Inline Classes
# ────────────────────────────────────────────────────────────────
class ContentInline(admin.TabularInline):
    """نمایش محتواهای مرتبط در صفحه دسته‌بندی"""
    model = Content.category.through
    extra = 0
    autocomplete_fields = ('content',)
    verbose_name = 'محتوای مرتبط'
    verbose_name_plural = 'محتواهای مرتبط'


# ────────────────────────────────────────────────────────────────
# Tag Admin (مدیریت برچسب‌های سفارشی)
# ────────────────────────────────────────────────────────────────
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """پنل مدیریت اختصاصی و بومی برچسب‌ها"""
    list_display = ('id', 'name', 'slug', 'views_count', 'created_at')
    list_display_links = ('id', 'name')
    search_fields = ('name', 'slug')
    readonly_fields = ('created_at',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('-views_count', 'name')


# ────────────────────────────────────────────────────────────────
# Category Admin
# ────────────────────────────────────────────────────────────────
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """پنل مدیریت حرفه‌ای دسته‌بندی‌ها با پیش‌نمایش تصاویر"""

    list_display = (
        'id',
        'name',
        'slug',
        'parent_link',
        'icon_preview',
        'logo_preview',
        'is_active',
        'indexable',
        'order',
        'views_count',
        'created_at',
    )
    list_display_links = ('id', 'name')
    list_editable = ('is_active', 'indexable', 'order')
    list_per_page = 25
    ordering = ('order', 'name')
    date_hierarchy = 'created_at'

    list_filter = (
        'is_active',
        'indexable',
        'parent',
    )

    search_fields = ('name', 'slug', 'description', 'meta_title')
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ('parent',)
    readonly_fields = ('created_at', 'views_count')

    fieldsets = (
        ('اطلاعات اصلی دسته‌بندی', {
            'fields': ('name', 'slug', 'parent', 'order'),
        }),
        ('آیکون و لوگوی فیزیکی (محلی)', {
            'fields': ('icon', 'logo'),
        }),
        ('SEO و متا تگ‌ها', {
            'fields': ('meta_title', 'meta_description', 'indexable'),
            'classes': ('collapse',),
        }),
        ('تنظیمات انتشار و آمار', {
            'fields': ('description', 'is_active', 'views_count'),
        }),
        ('تاریخچه ثبت دیتابیس', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )

    # اتصال فقط به ContentInline (حذف کامل CategoryInline برای حل باگ تغییر والد)
    inlines = [ContentInline]

    @admin.display(description='آیکون')
    def icon_preview(self, obj):
        if obj.icon:
            return format_html(
                '<img src="{}" style="max-height:30px;max-width:30px;object-fit:contain;" />',
                obj.icon.url
            )
        return mark_safe('<span style="color:#aaa;">—</span>')

    @admin.display(description='لوگو دسته‌بندی')
    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="max-height:35px;max-width:80px;object-fit:contain;border-radius:3px;" />',
                obj.logo.url
            )
        return mark_safe('<span style="color:#aaa;">—</span>')

    @admin.display(description='دسته والد')
    def parent_link(self, obj):
        if obj.parent:
            return format_html(
                '<a href="{}">{}</a>',
                f'/admin/contents/category/{obj.parent.id}/change/',
                obj.parent.name
            )
        return mark_safe(
            '<span style="color:#888;">— بدون والد —</span>'
        )

    @admin.action(description='فعال کردن دسته‌بندی‌های انتخاب‌شده')
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} دسته‌بندی فعال شد.')

    @admin.action(description='غیرفعال کردن دسته‌بندی‌های انتخاب‌شده')
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} دسته‌بندی غیرفعال شد.')

    @admin.action(description='قابل ایندکس کردن')
    def make_indexable(self, request, queryset):
        updated = queryset.update(indexable=True)
        self.message_user(request, f'{updated} دسته‌بندی قابل ایندکس شد.')

    @admin.action(description='غیرقابل ایندکس کردن')
    def make_noindex(self, request, queryset):
        updated = queryset.update(indexable=False)
        self.message_user(request, f'{updated} دسته‌بندی غیرقابل ایندکس شد.')

    actions = [make_active, make_inactive, make_indexable, make_noindex]


# ────────────────────────────────────────────────────────────────
# MediaContainer Admin
# ────────────────────────────────────────────────────────────────
@admin.register(MediaContainer)
class MediaContainerAdmin(admin.ModelAdmin):
    """پنل مدیریت حرفه‌ای رسانه‌ها"""

    list_display = (
        'id',
        'media_type',
        'thumbnail_preview',
        'is_used',
        'is_analyzed',
        'source_url_link',
        'original_size_kb',
        'created_at',
    )
    list_display_links = ('id', 'media_type')
    list_editable = ('is_used', 'is_analyzed')
    list_per_page = 25
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    list_filter = (
        'media_type',
        'is_used',
        'is_analyzed',
        ('created_at', admin.DateFieldListFilter),
    )

    search_fields = ('source_url', 'description', 'alt_text')
    readonly_fields = ('created_at', 'updated_at', 'original_width', 'original_height', 'original_size_kb')

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('media_type', 'media'),
        }),
        ('ابعاد و حجم', {
            'fields': ('original_width', 'original_height', 'original_size_kb'),
            'classes': ('collapse',),
        }),
        ('توضیحات و منبع', {
            'fields': ('description', 'alt_text', 'source_url', 'is_used', 'is_analyzed'),
        }),
        ('تاریخچه', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='پیش‌نمایش')
    def thumbnail_preview(self, obj):
        if obj.media_type == MediaContainer.MediaTypes.IMAGE and obj.media:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height:60px;max-width:120px;border-radius:4px;" /></a>',
                obj.media.url, obj.media.url
            )
        elif obj.media_type == MediaContainer.MediaTypes.VIDEO and obj.media:
            return mark_safe(
                '<span style="color:#007bff;font-size:12px;">📹 ویدیو</span>'
            )
        return mark_safe('<span style="color:#888;">—</span>')

    @admin.display(description='منبع')
    def source_url_link(self, obj):
        if obj.source_url:
            return format_html(
                '<a href="{}" target="_blank" style="color:#007bff;">🔗 مشاهده منبع</a>',
                obj.source_url
            )
        return '-'

    @admin.action(description='علامت‌گذاری به‌عنوان استفاده‌شده')
    def make_used(self, request, queryset):
        updated = queryset.update(is_used=True)
        self.message_user(request, f'{updated} رسانه علامت‌گذاری شد.')

    @admin.action(description='علامت‌گذاری به‌عنوان استفاده‌نشده')
    def make_unused(self, request, queryset):
        updated = queryset.update(is_used=False)
        self.message_user(request, f'{updated} رسانه علامت‌گذاری شد.')

    actions = [make_used, make_unused]


# ────────────────────────────────────────────────────────────────
# Content Admin
# ────────────────────────────────────────────────────────────────
@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    """پنل مدیریت حرفه‌ای محتواها"""

    list_display = (
        'id',
        'title_short',
        'author',
        'status_badge',
        'importance_badge',
        'content_type_badge',
        'suggestions_status_badge',
        'views_count',
        'indexable',
        'publish_date',
        'created_at',
    )
    list_display_links = ('id', 'title_short')
    list_per_page = 25
    ordering = ('-publish_date', '-created_at')
    date_hierarchy = 'publish_date'

    list_filter = (
        'status',
        'importance',
        'schema_type',
        'suggestions_status',
        'indexable',
        'category',
        'tags',
        ('publish_date', admin.DateFieldListFilter),
        ('created_at', admin.DateFieldListFilter),
    )

    search_fields = ('title', 'slug', 'summary', 'author', 'short_code', 'meta_title')
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('category', 'featured_media')

    filter_horizontal = ('category', 'tags')

    readonly_fields = (
        'short_code',
        'views_count',
        'likes_count',
        'share_count',
        'reading_time',
        'created_at',
        'updated_at',
        'external_id',
        'data_source',
    )

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('title', 'slug', 'summary', 'content'),
        }),
        ('دسته‌بندی و برچسب', {
            'fields': ('category', 'tags'),
        }),
        ('رسانه', {
            'fields': ('featured_media', 'media_thumbnail', 'media_image_small'),
            'classes': ('collapse',),
        }),
        ('SEO و Schema', {
            'fields': ('schema_type', 'meta_title', 'meta_description', 'canonical_url', 'indexable'),
            'classes': ('collapse',),
        }),
        ('وضعیت و زمان‌بندی', {
            'fields': ('status', 'importance', 'suggestions_status', 'publish_date'),
        }),
        ('نویسنده و آمار', {
            'fields': ('author', 'views_count', 'likes_count', 'share_count', 'reading_time'),
            'classes': ('collapse',),
        }),
        ('کد کوتاه، منبع و تاریخچه', {
            'fields': ('short_code', 'data_source', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='عنوان', ordering='title')
    def title_short(self, obj):
        title = obj.title or 'بدون عنوان'
        if len(title) > 40:
            return f'{title[:40]}…'
        return title

    @admin.display(description='وضعیت')
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'published': '#28a745',
            'archived': '#fd7e14',
        }
        labels = dict(Content.StatusChoices.choices)
        color = colors.get(obj.status, '#6c757d')
        label = labels.get(obj.status, obj.status)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{}</span>',
            color, label
        )

    @admin.display(description='اهمیت')
    def importance_badge(self, obj):
        colors = {
            1: '#6c757d',
            2: '#dc3545',
            3: '#ffc107',
        }
        labels = dict(Content.ImportanceChoices.choices)
        color = colors.get(obj.importance, '#6c757d')
        label = labels.get(obj.importance, obj.importance)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{}</span>',
            color, label
        )

    @admin.display(description='نوع محتوا')
    def content_type_badge(self, obj):
        labels = dict(Content.ContentTypeChoices.choices)
        label = labels.get(obj.schema_type, obj.schema_type)
        return format_html(
            '<span style="background:#17a2b8;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{}</span>',
            label
        )

    @admin.display(description='وضعیت تصاویر پیشنهادی')
    def suggestions_status_badge(self, obj):
        colors = {
            Content.Suggestions.EMPTY: '#6c757d',
            Content.Suggestions.WAITING: '#ffc107',
            Content.Suggestions.PROCESSING: '#17a2b8',
            Content.Suggestions.FAILED: '#dc3545',
            Content.Suggestions.FINISHED: '#28a745',
        }
        labels = dict(Content.Suggestions.choices)
        color = colors.get(obj.suggestions_status, '#6c757d')
        label = labels.get(obj.suggestions_status, obj.suggestions_status)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">{}</span>',
            color, label
        )

    @admin.action(description='انتشار موارد انتخاب‌شده')
    def make_published(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status=Content.StatusChoices.PUBLISHED, publish_date=timezone.now())
        self.message_user(request, f'{updated} محتوا منتشر شد.')

    @admin.action(description='بایگانی موارد انتخاب‌شده')
    def make_archived(self, request, queryset):
        updated = queryset.update(status=Content.StatusChoices.ARCHIVED)
        self.message_user(request, f'{updated} محتوا بایگانی شد.')

    @admin.action(description='پیش‌نویس کردن موارد انتخاب‌شده')
    def make_draft(self, request, queryset):
        updated = queryset.update(status=Content.StatusChoices.DRAFT, publish_date=None)
        self.message_user(request, f'{updated} محتوا به پیش‌نویس تبدیل شد.')

    @admin.action(description='بهینه‌سازی سئو و تگ‌گذاری مجدد با هوش مصنوعی')
    def trigger_seo_optimization(self, request, queryset):
        from workflows.tasks import process_seo_workflow
        triggered = 0
        for obj in queryset:
            process_seo_workflow.delay(obj.id)
            triggered += 1
        self.message_user(request, f'تسک بهینه‌سازی سئو برای {triggered} مقاله با موفقیت به صف سلری ارسال شد.')

    @admin.action(description='ریست بازدیدها')
    def reset_views(self, request, queryset):
        updated = queryset.update(views_count=0)
        self.message_user(request, f'{updated} بازدید ریست شد.')

    @admin.action(description='ریست لایک‌ها')
    def reset_likes(self, request, queryset):
        updated = queryset.update(likes_count=0)
        self.message_user(request, f'{updated} لایک ریست شد.')

    @admin.action(description='ریست اشتراک‌گذاری‌ها')
    def reset_shares(self, request, queryset):
        updated = queryset.update(share_count=0)
        self.message_user(request, f'{updated} اشتراک‌گذاری ریست شد.')

    @admin.action(description='علامت‌گذاری به‌عنوان ویژه')
    def make_featured(self, request, queryset):
        updated = queryset.update(importance=Content.ImportanceChoices.FEATURED)
        self.message_user(request, f'{updated} محتوا ویژه شد.')

    @admin.action(description='علامت‌گذاری به‌عنوان عادی')
    def make_normal(self, request, queryset):
        updated = queryset.update(importance=Content.ImportanceChoices.NORMAL)
        self.message_user(request, f'{updated} محتوا عادی شد.')

    actions = [
        make_published,
        make_archived,
        make_draft,
        trigger_seo_optimization,
        reset_views,
        reset_likes,
        reset_shares,
        make_featured,
        make_normal,
    ]


# ────────────────────────────────────────────────────────────────
# PostsContainer Admin
# ────────────────────────────────────────────────────────────────
@admin.register(PostsContainer)
class PostsContainerAdmin(admin.ModelAdmin):
    """پنل مدیریت حرفه‌ای پست‌های تلگرام"""

    list_display = (
        'id',
        'content_short',
        'state_badge',
        'main_article_link',
        'medias_count',
        'suggestions_status_badge',
        'created_at',
        'sent_at'
    )
    list_display_links = ('id', 'content_short')
    list_per_page = 25
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    list_filter = (
        'state',
        'suggestions_status',
        ('created_at', admin.DateFieldListFilter),
        ('sent_at', admin.DateFieldListFilter),
    )

    search_fields = ('content', 'main_article__title')
    filter_horizontal = ('medias',)
    readonly_fields = ('created_at', 'sent_at', 'data_source')

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('content', 'main_article', 'data_source'),
        }),
        ('رسانه‌ها و تصاویر پیشنهادی', {
            'fields': ('medias', 'suggestions_status', 'suggestions'),
        }),
        ('وضعیت انتشار و زمان‌بندی', {
            'fields': ('state', 'created_at', 'sent_at'),
        }),
    )

    @admin.display(description='متن پست', ordering='content')
    def content_short(self, obj):
        if obj.content and len(obj.content) > 50:
            return f"{obj.content[:50]}..."
        return obj.content or 'بدون محتوا'

    @admin.display(description='وضعیت ارسال')
    def state_badge(self, obj):
        if obj.state == PostsContainer.State.SENT:
            return mark_safe(
                '<span style="background:#28a745;color:#fff;padding:2px 10px;border-radius:4px;font-size:12px;">ارسال شده</span>'
            )
        return mark_safe(
            '<span style="background:#6c757d;color:#fff;padding:2px 10px;border-radius:4px;font-size:12px;">پیش‌نویس</span>'
        )

    @admin.display(description='مقاله مرتبط')
    def main_article_link(self, obj):
        if obj.main_article:
            return format_html(
                '<a href="/admin/contents/content/{}/change/">{}</a>',
                obj.main_article.id, obj.main_article.title[:30]
            )
        return mark_safe('<span style="color:#888;">بدون مقاله</span>')

    @admin.display(description='تعداد رسانه‌ها')
    def medias_count(self, obj):
        count = obj.medias.count()
        return format_html(
            '<span style="background:#007bff;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">{}</span>',
            count
        )

    @admin.display(description='وضعیت تصاویر پیشنهادی')
    def suggestions_status_badge(self, obj):
        colors = {
            PostsContainer.Suggestions.EMPTY: '#6c757d',
            PostsContainer.Suggestions.WAITING: '#ffc107',
            PostsContainer.Suggestions.PROCESSING: '#17a2b8',
            PostsContainer.Suggestions.FAILED: '#dc3545',
            PostsContainer.Suggestions.FINISHED: '#28a745',
        }
        labels = dict(PostsContainer.Suggestions.choices)
        color = colors.get(obj.suggestions_status, '#6c757d')
        label = labels.get(obj.suggestions_status, obj.suggestions_status)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">{}</span>',
            color, label
        )

    @admin.action(description='ارسال و انتشار متمرکز به تلگرام و وب‌سایت')
    def trigger_publishing(self, request, queryset):
        from workflows.tasks import process_publisher_workflow
        triggered = 0
        for obj in queryset:
            process_publisher_workflow.delay(obj.id)
            triggered += 1
        self.message_user(request, f'فرآیند انتشار متمرکز برای {triggered} پست به صف سلری فرستاده شد.')

    @admin.action(description='بازنشانی وضعیت به پیش‌نویس')
    def reset_to_draft(self, request, queryset):
        updated = queryset.update(state=PostsContainer.State.DRAFT, sent_at=None)
        self.message_user(request, f'وضعیت {updated} پست به حالت پیش‌نویس بازنشانی شد.')

    actions = [trigger_publishing, reset_to_draft]
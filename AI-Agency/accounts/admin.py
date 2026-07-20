from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import ApiContainer, Comment


@admin.register(ApiContainer)
class ApiContainerAdmin(admin.ModelAdmin):
    """پنل مدیریت حرفه‌ای کلیدهای API"""

    # ── نمایش لیست ──────────────────────────────────────────
    list_display = (
        'id',
        'provider',
        'key_masked',
        'today_use',
        'total_use',
        'status_badge',
        'created',
        'updated',
    )

    list_display_links = ('id', 'provider')
    list_per_page = 25
    ordering = ('-created',)
    date_hierarchy = 'created'

    # ── فیلترها و جستجو ─────────────────────────────────────
    list_filter = (
        'provider',
        'status',
        ('created', admin.DateFieldListFilter),
        ('updated', admin.DateFieldListFilter),
    )

    search_fields = ('key', 'provider')
    readonly_fields = ('today_use', 'total_use', 'created', 'updated')

    # ── فرم ویرایش ──────────────────────────────────────────
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('provider', 'key'),
        }),
        ('آمار استفاده', {
            'fields': ('today_use', 'total_use'),
            'classes': ('collapse',),
        }),
        ('تنظیمات', {
            'fields': ('status',),
        }),
        ('تاریخچه', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',),
        }),
    )

    # ── ستون‌های سفارشی ────────────────────────────────────
    @admin.display(description='کلید API', ordering='key')
    def key_masked(self, obj):
        if obj.key and len(obj.key) > 8:
            return f"{obj.key[:4]}***{obj.key[-4:]}"
        return obj.key or '-'

    @admin.display(description='وضعیت')
    def status_badge(self, obj):
        if obj.status:
            return mark_safe(
                '<span style="background:#28a745;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">فعال</span>'
            )
        return mark_safe(
            '<span style="background:#dc3545;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">غیرفعال</span>'
        )

    # ── اکشن‌ها ─────────────────────────────────────────────
    @admin.action(description='فعال کردن موارد انتخاب‌شده')
    def make_active(self, request, queryset):
        updated = queryset.update(status=True)
        self.message_user(request, f'{updated} کلید API با موفقیت فعال شد.')

    @admin.action(description='غیرفعال کردن موارد انتخاب‌شده')
    def make_inactive(self, request, queryset):
        updated = queryset.update(status=False)
        self.message_user(request, f'{updated} کلید API با موفقیت غیرفعال شد.')

    @admin.action(description='ریست مصرف امروز')
    def reset_today_use(self, request, queryset):
        updated = queryset.update(today_use=0)
        self.message_user(request, f'{updated} کلید API ریست شد.')

    @admin.action(description='ریست مصرف کلی')
    def reset_total_use(self, request, queryset):
        updated = queryset.update(total_use=0)
        self.message_user(request, f'{updated} کلید API ریست شد.')

    actions = [make_active, make_inactive, reset_today_use, reset_total_use]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """پنل مدیریت مانیتورینگ و نظارت بر دیدگاه‌های کاربران"""

    # ── نمایش لیست ──────────────────────────────────────────
    list_display = (
        'id',
        'name',
        'content_link',
        'short_text',
        'status_badge',
        'created_at',
        'likes_count',
    )
    list_display_links = ('id', 'name')
    list_per_page = 25
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    # ── فیلترها و جستجو ─────────────────────────────────────
    list_filter = (
        'status',
        ('created_at', admin.DateFieldListFilter),
    )
    search_fields = ('name', 'email', 'text', 'content__title')
    readonly_fields = ('created_at',)

    # ── فرم ویرایش ──────────────────────────────────────────
    fieldsets = (
        ('اطلاعات کاربری فرستنده', {
            'fields': ('name', 'email'),
        }),
        ('ارتباطات و محتوا', {
            'fields': ('content', 'parent', 'text'),
        }),
        ('وضعیت انتشار و آمار دیدگاه', {
            'fields': ('status', 'likes_count', 'created_at'),
        }),
    )

    # ── ستون‌های سفارشی ────────────────────────────────────
    @admin.display(description='دیدگاه مرتبط')
    def content_link(self, obj):
        if obj.content:
            return format_html(
                '<a href="/admin/contents/content/{}/change/">{}</a>',
                obj.content.id, obj.content.title[:30]
            )
        return '-'

    @admin.display(description='خلاصه دیدگاه')
    def short_text(self, obj):
        if obj.text and len(obj.text) > 60:
            return f"{obj.text[:60]}..."
        return obj.text or '-'

    @admin.display(description='وضعیت تایید')
    def status_badge(self, obj):
        colors = {
            Comment.CommentStatus.UNDER_REVIEW: '#ffc107',  # زرد
            Comment.CommentStatus.APPROVED: '#28a745',      # سبز
            Comment.CommentStatus.REJECTED: '#dc3545',      # قرمز
        }
        labels = dict(Comment.CommentStatus.choices)
        color = colors.get(obj.status, '#6c757d')
        label = labels.get(obj.status, obj.status)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:4px;font-size:11px;">{}</span>',
            color, label
        )

    # ── اکشن‌های دسته‌جمعی تایید نظرات ─────────────────────────
    @admin.action(description='تایید و انتشار دیدگاه‌های انتخاب‌شده')
    def approve_comments(self, request, queryset):
        updated = queryset.update(status=Comment.CommentStatus.APPROVED)
        self.message_user(request, f'تعداد {updated} دیدگاه تایید و در سایت منتشر شدند.')

    @admin.action(description='رد دیدگاه‌های انتخاب‌شده')
    def reject_comments(self, request, queryset):
        updated = queryset.update(status=Comment.CommentStatus.REJECTED)
        self.message_user(request, f'تعداد {updated} دیدگاه رد شدند.')

    @admin.action(description='انتقال دیدگاه‌های انتخاب‌شده به بررسی مجدد')
    def review_comments(self, request, queryset):
        updated = queryset.update(status=Comment.CommentStatus.UNDER_REVIEW)
        self.message_user(request, f'تعداد {updated} دیدگاه به وضعیت در حال بررسی بازگشتند.')

    actions = [approve_comments, reject_comments, review_comments]
import json
from datetime import datetime
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from workflows.models import ReceivedMessages, WorkflowLog


@admin.register(ReceivedMessages)
class ReceivedMessagesAdmin(admin.ModelAdmin):
    """پنل مدیریت حرفه‌ای پیام‌های دریافتی"""

    list_display = (
        'id',
        'step_badge',
        'is_tech_badge',
        'is_exists_badge',
        'is_finished_badge',
        'medias_count',
    )
    list_display_links = ('id', 'step_badge')
    list_per_page = 25
    ordering = ('-id',)

    list_filter = (
        'step',
        'is_tech',
        'is_exists',
        'is_finished',
    )

    search_fields = ('raw_text', 'links')
    readonly_fields = ('get_step_name',)

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('raw_text', 'links'),
        }),
        ('مراحل پردازش', {
            'fields': ('step', 'get_step_name', 'is_tech', 'is_exists', 'is_finished'),
        }),
        ('رسانه‌های مرتبط', {
            'fields': ('medias',),
        }),
    )

    filter_horizontal = ('medias',)
    autocomplete_fields = ('medias',)

    @admin.display(description='مرحله', ordering='step')
    def step_badge(self, obj):
        colors = {
            ReceivedMessages.Steps.OBSERVING: '#6c757d',   # tech_check
            ReceivedMessages.Steps.CHECKING: '#17a2b8',    # exists_check
            ReceivedMessages.Steps.FETCHING: '#ffc107',    # fetching_links
            ReceivedMessages.Steps.ANALYZING: '#fd7e14',   # analyzing_medias
            ReceivedMessages.Steps.SAVING: '#007bff',      # saving_medias
            ReceivedMessages.Steps.FINISHED: '#28a745',    # completed
        }
        color = colors.get(obj.step, '#6c757d')
        label = obj.get_step_name()
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:4px;font-size:12px;">{}</span>',
            color, label
        )

    @admin.display(description='تکنیکال')
    def is_tech_badge(self, obj):
        if obj.is_tech:
            return mark_safe('<span style="color:#28a745;font-weight:bold;">✔ بله</span>')
        return mark_safe('<span style="color:#dc3545;">✘ خیر</span>')

    @admin.display(description='موجود')
    def is_exists_badge(self, obj):
        if obj.is_exists:
            return mark_safe('<span style="color:#28a745;font-weight:bold;">✔ بله</span>')
        return mark_safe('<span style="color:#dc3545;">✘ خیر</span>')

    @admin.display(description='تمام‌شده')
    def is_finished_badge(self, obj):
        if obj.is_finished:
            return mark_safe('<span style="color:#28a745;font-weight:bold;">✔ بله</span>')
        return mark_safe('<span style="color:#dc3545;">✘ خیر</span>')

    @admin.display(description='تعداد رسانه‌ها')
    def medias_count(self, obj):
        count = obj.medias.count()
        return format_html(
            '<span style="background:#007bff;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">{}</span>',
            count
        )

    # ── اکشن‌ها ─────────────────────────────────────────────
    @admin.action(description='اجرای مجدد کل زنجیره پردازش (Celery Task)')
    def retrigger_workflow(self, request, queryset):
        from workflows.tasks import process_received_message
        triggered = 0
        for obj in queryset:
            process_received_message.delay(obj.id)
            triggered += 1
        self.message_user(request, f'اجرای تسک تحلیل اولیه برای {triggered} پیام به ورکر سلری ارسال شد.')

    @admin.action(description='بازنشانی به مرحله اول (مشاهده)')
    def reset_to_observing(self, request, queryset):
        updated = queryset.update(step=ReceivedMessages.Steps.OBSERVING, is_finished=False)
        self.message_user(request, f'{updated} پیام به مرحله اول بازنشانی شد.')

    @admin.action(description='تکمیل کردن پیام‌ها')
    def mark_finished(self, request, queryset):
        updated = queryset.update(is_finished=True, step=ReceivedMessages.Steps.FINISHED)
        self.message_user(request, f'{updated} پیام تکمیل شد.')

    @admin.action(description='انتقال به مرحله بعد')
    def advance_step(self, request, queryset):
        count = 0
        for msg in queryset:
            if msg.next_step():
                count += 1
        self.message_user(request, f'{count} پیام به مرحله بعد منتقل شد.')

    @admin.action(description='بازگشت به مرحله قبل')
    def revert_step(self, request, queryset):
        count = 0
        for msg in queryset:
            if msg.prev_step():
                count += 1
        self.message_user(request, f'{count} پیام به مرحله قبل بازگشت.')

    @admin.action(description='علامت‌گذاری به‌عنوان تکنیکال')
    def mark_tech(self, request, queryset):
        updated = queryset.update(is_tech=True)
        self.message_user(request, f'{updated} پیام تکنیکال علامت‌گذاری شد.')

    @admin.action(description='علامت‌گذاری به‌عنوان غیرتکنیکال')
    def make_non_tech(self, request, queryset):
        updated = queryset.update(is_tech=False)
        self.message_user(request, f'{updated} پیام غیرتکنیکال علامت‌گذاری شد.')

    @admin.action(description='علامت‌گذاری به‌عنوان موجود')
    def mark_exists(self, request, queryset):
        updated = queryset.update(is_exists=True)
        self.message_user(request, f'{updated} پیام موجود علامت‌گذاری شد.')

    @admin.action(description='علامت‌گذاری به‌عنوان غیرموجود')
    def make_non_exists(self, request, queryset):
        updated = queryset.update(is_exists=False)
        self.message_user(request, f'{updated} پیام غیرموجود علامت‌گذاری شد.')

    actions = [
        retrigger_workflow,
        reset_to_observing,
        advance_step,
        revert_step,
        mark_finished,
        mark_tech,
        make_non_tech,
        mark_exists,
        make_non_exists,
    ]


@admin.register(WorkflowLog)
class WorkflowLogAdmin(admin.ModelAdmin):
    """پنل نظارتی حرفه‌ای و مانیتورینگ تایم‌لاین‌های سیستم عاملی لنگ‌چین"""

    list_display = ('message_id', 'status_badge', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('message__raw_text', 'message__id')

    readonly_fields = (
        'message_link',
        'display_timeline',
        'display_metadata',
        'status',
        'created_at',
        'updated_at'
    )
    exclude = ('message', 'timeline_events', 'metadata')

    @admin.display(description='وضعیت کل زنجیره')
    def status_badge(self, obj):
        colors = {
            WorkflowLog.StatusChoices.RUNNING: '#ffc107',
            WorkflowLog.StatusChoices.COMPLETED: '#28a745',
            WorkflowLog.StatusChoices.SKIPPED: '#6c757d',
            WorkflowLog.StatusChoices.FAILED: '#dc3545',
        }
        labels = dict(WorkflowLog.StatusChoices.choices)
        color = colors.get(obj.status, '#6c757d')
        label = labels.get(obj.status, obj.status)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:4px;font-size:12px;">{}</span>',
            color, label
        )

    def message_link(self, obj):
        if obj.message:
            return format_html(
                '<a href="/admin/workflows/receivedmessages/{}/change/">نمایش پیام دریافتی خام #{}</a>',
                obj.message.id, obj.message.id
            )
        return "-"

    message_link.short_description = "پیام دریافتی مرتبط"

    def display_timeline(self, obj):
        """نمایش زیبای وقایع ثبت شده به همراه محاسبه هوشمند اختلاف زمانی ثانیه‌ها بین گام‌ها"""
        if not obj.timeline_events:
            return "هیچ رویدادی ثبت نشده است."

        events_html = []
        prev_time_dt = None

        for ev in obj.timeline_events:
            step = ev.get("step", "UNKNOWN")
            timestamp_str = ev.get("timestamp")
            message = ev.get("message")
            details = ev.get("details")

            current_time_dt = None
            duration_text = ""
            if timestamp_str:
                try:
                    current_time_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    if prev_time_dt:
                        diff_seconds = int((current_time_dt - prev_time_dt).total_seconds())
                        if diff_seconds < 60:
                            duration_text = f"⏱️ مدت زمان این مرحله: {diff_seconds} ثانیه"
                        else:
                            minutes = diff_seconds // 60
                            seconds = diff_seconds % 60
                            duration_text = f"⏱️ مدت زمان این مرحله: {minutes} دقیقه و {seconds} ثانیه"
                    else:
                        duration_text = "🚀 شروع فرآیند سیستم"
                except Exception:
                    pass

            if current_time_dt:
                prev_time_dt = current_time_dt

            border_color = "#417690"
            if "CRITICAL" in step or "ERROR" in step or "FAIL" in step:
                border_color = "#ba2121"
            elif "WRITER" in step:
                border_color = "#26b99a"
            elif "SEO" in step:
                border_color = "#9b59b6"
            elif "PUBLISHER" in step:
                border_color = "#2ecc71"

            details_html = ""
            if details:
                formatted_details = json.dumps(details, ensure_ascii=False, indent=2)
                details_html = format_html(
                    '<pre style="margin: 6px 0 0 0; font-family: monospace; font-size: 11px; background: #f1f1f1; padding: 8px; border-radius: 4px; overflow-x: auto; color: #555;">{}</pre>',
                    formatted_details
                )

            event_item = format_html(
                '<div style="margin-bottom: 12px; padding: 10px; border-right: 4px solid {}; background: #fdfdfd; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">'
                '<div style="display: flex; justify-content: space-between; font-size: 11px; color: #666; margin-bottom: 6px;">'
                '<span><strong>گام: {}</strong></span>'
                '<span style="font-weight: bold; color: #2b547e;">{} | زمان: {}</span>'
                '</div>'
                '<div style="font-size: 13px; color: #333; margin-bottom: 4px;">{}</div>'
                '{}'
                '</div>',
                border_color,
                step,
                duration_text,
                timestamp_str,
                message,
                details_html
            )
            events_html.append(event_item)

        joined_events = mark_safe("".join(events_html))

        return format_html(
            '<div style="font-family: Tahoma, sans-serif; line-height: 1.6; max-height: 600px; overflow-y: auto;">{}</div>',
            joined_events
        )

    display_timeline.short_description = "تایم‌لاین رویدادهای فرآیند"

    def display_metadata(self, obj):
        """نمایش ساختاریافته کل دیتای متادیتا"""
        if not obj.metadata:
            return "داده متادیتایی یافت نشد."
        formatted_meta = json.dumps(obj.metadata, ensure_ascii=False, indent=2)
        return format_html(
            '<pre style="font-family: monospace; font-size: 11px; background: #f5f5f5; padding: 10px; border-radius: 4px; max-height: 400px; overflow-y: auto;">{}</pre>',
            formatted_meta
        )

    display_metadata.short_description = "خروجی‌های سیستمی و متادیتا"
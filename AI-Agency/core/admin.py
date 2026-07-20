from django.contrib import admin
from django.contrib.admin import AdminSite

# ── تنظیمات ظاهری پنل مدیریت ───────────────────────────────
admin.site.site_header = 'پنل مدیریت خبرگزاری'
admin.site.site_title = 'پنل مدیریت'
admin.site.index_title = 'داشبورد مدیریتی'

# ── می‌توانید AdminSite سفارشی بسازید ───────────────────────
# class CustomAdminSite(AdminSite):
#     site_header = 'پنل مدیریت سفارشی'
#     site_title = 'مدیریت'
#     index_title = 'خوش آمدید'
#
# admin_site = CustomAdminSite(name='custom_admin')

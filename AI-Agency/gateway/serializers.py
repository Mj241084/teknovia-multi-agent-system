# gateway/serializers.py
import re
from rest_framework import serializers
from contents.models import Content, Category, Tag, MediaContainer
from accounts.models import Comment
from workflows.vector_services import get_similar_article_objects


# ────────────────────────────────────────────────────────────────
# متدهای کمکی مبدل مارک‌داون اختصاصی به مارک‌داون استاندارد وب
# ────────────────────────────────────────────────────────────────

def replace_media_ids_with_urls(markdown_content: str, request=None) -> str:
    """
    شناسایی الگوهای اختصاصی دیتابیس نظیر ![alt](media_id:ID) و تبدیل آنها
    به لینک‌های مستقیم و مطلق ابری روی آروان‌کلود برای رندر استاندارد در فرانت‌اند.
    این متد کوئری‌ها را تجمیع می‌کند تا از وقوع خطای کارایی N+1 جلوگیری شود.
    """
    if not markdown_content:
        return ""

    # ۱. استخراج تمام الگوهای رسانه‌ای موجود در مارک‌داون مقاله
    pattern = r"!\[(.*?)\]\(media_id:(\d+)\)"
    matches = re.findall(pattern, markdown_content)
    if not matches:
        return markdown_content

    # ۲. استخراج لیست شناسه‌ها برای اجرای یک کوئری دسته‌جمعی بهینه
    media_ids = [int(m[1]) for m in matches]

    # ۳. واکشی رسانه‌ها و ساخت نگاشت شناسه به آدرس فایل ابری
    media_map = {}
    containers = MediaContainer.objects.filter(id__in=media_ids)
    for container in containers:
        if container.media:
            # ساخت آدرس مطلق اینترنتی در صورت حضور درخواست (Request)
            url = request.build_absolute_uri(container.media.url) if request else container.media.url
            media_map[container.id] = url

    # ۴. جایگزینی الگوها با آدرس‌های استاندارد و معتبر وب
    def replacer(match):
        alt_text = match.group(1)
        media_id = int(match.group(2))
        actual_url = media_map.get(media_id)
        if actual_url:
            return f"![{alt_text}]({actual_url})"
        # در صورت نبود فایل یا حذف شدن فیزیکی، آدرس تصویر خالی گذاشته می‌شود
        return f"![{alt_text}]()"

    return re.sub(pattern, replacer, markdown_content)


# ────────────────────────────────────────────────────────────────
# کلاس‌های سریالایزر (Serializers Implementation)
# ────────────────────────────────────────────────────────────────

class MediaContainerSerializer(serializers.ModelSerializer):
    """سریالایزر کامل اطلاعات چندرسانه‌ای به همراه جزییات ابعاد و آدرس فایل"""
    media_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaContainer
        fields = [
            'id',
            'media_type',
            'media_url',
            'alt_text',
            'description',
            'original_width',
            'original_height',
            'original_size_kb'
        ]

    def get_media_url(self, obj):
        if obj.media:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.media.url)
            return obj.media.url
        return None


class CategorySerializer(serializers.ModelSerializer):
    """سریالایزر اطلاعات اولیه دسته‌بندی‌ها به همراه لوگو، آیکون و فیلدهای کامل سئو"""
    logo_url = serializers.SerializerMethodField()
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'logo_url',
            'icon_url',
            'order',
            'views_count',
            'indexable',      # فیلد مدیریت ایندکس بودن در گوگل
            'meta_title',     # عنوان سئو شده اختصاصی دیتابیس
            'meta_description'# توضیحات سئو شده اختصاصی دیتابیس
        ]

    def get_logo_url(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

    def get_icon_url(self, obj):
        if obj.icon:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.icon.url)
            return obj.icon.url
        return None


class CategoryTreeSerializer(serializers.ModelSerializer):
    """سریالایزر درختی و بازگشتی دسته‌بندی‌ها با زیرمجموعه‌های نامحدود به همراه فایل‌های سئو"""
    children = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'views_count',
            'logo_url',
            'icon_url',
            'order',
            'indexable',
            'meta_title',
            'meta_description',
            'children'
        ]

    def get_children(self, obj):
        # بازخوانی فرزندان فعال این شاخه بر اساس اولویت ترتیب
        active_children = obj.children.filter(is_active=True).order_by('order', 'name')
        return CategoryTreeSerializer(active_children, many=True, context=self.context).data

    def get_logo_url(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

    def get_icon_url(self, obj):
        if obj.icon:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.icon.url)
            return obj.icon.url
        return None


class ContentTagSerializer(serializers.ModelSerializer):
    """سریالایزر برچسب سفارشی به همراه آمار بازدید تگ"""

    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'views_count']


class ContentListSerializer(serializers.ModelSerializer):
    """سریالایزر غنی و بهینه شده مقالات برای نمایش در انواع لیست‌ها و ویجت‌ها"""
    featured_media = MediaContainerSerializer(read_only=True)
    categories = CategorySerializer(source='category', many=True, read_only=True)
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            'id',
            'title',
            'slug',
            'summary',
            'reading_time',
            'publish_date',
            'views_count',
            'likes_count',
            'share_count',
            'featured_media',
            'categories',
            'tags'
        ]

    def get_tags(self, obj):
        # استخراج برچسب‌های متصل به مقاله
        tags_queryset = obj.tags.all()
        return [tag.name for tag in tags_queryset]


class SimilarArticleSerializer(serializers.ModelSerializer):
    """سریالایزر سبک مقالات مشابه به همراه اطلاعات تصویر شاخص"""
    featured_media_url = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = ['id', 'title', 'slug', 'summary', 'publish_date', 'featured_media_url']

    def get_featured_media_url(self, obj):
        if obj.featured_media and obj.featured_media.media:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.featured_media.media.url)
            return obj.featured_media.media.url
        return None


class ContentDetailSerializer(serializers.ModelSerializer):
    """سریالایزر تفصیلی مقاله به همراه تبدیل هوشمند محتوا به مارک‌داون استاندارد وب"""
    featured_media = MediaContainerSerializer(read_only=True)
    categories = CategorySerializer(source='category', many=True, read_only=True)
    tags = serializers.SerializerMethodField()
    similar_articles = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()

    # فیلد پویا جهت تبدیل و تحویل متن مارک‌داون استاندارد به فرانت‌انداسترو
    content = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            'id',
            'title',
            'slug',
            'summary',
            'content',
            'reading_time',
            'views_count',
            'likes_count',
            'share_count',
            'meta_title',
            'meta_description',
            'canonical_url',
            'publish_date',
            'featured_media',
            'categories',
            'tags',
            'comments_count',
            'similar_articles',
            'short_code'  # اضافه شدن کد کوتاه یکتا جهت اشتراک گذاری کوتاه
        ]

    def get_content(self, obj):
        # مهار و تبدیل کدهای درون‌متنی به آدرس‌های ابری واقعی S3 پیش از تحویل
        request = self.context.get('request')
        return replace_media_ids_with_urls(obj.content, request)

    def get_tags(self, obj):
        tags_queryset = obj.tags.all()
        return [tag.name for tag in tags_queryset]

    def get_comments_count(self, obj):
        # شمارش فقط کامنت‌های تایید شده
        return obj.comments.filter(status=Comment.CommentStatus.APPROVED).count()

    def get_similar_articles(self, obj):
        # استخراج همگام‌سازی شده ۵ مقاله مشابه بر اساس تشابه برداری TurboVec
        if obj.embedding_data:
            try:
                similar_objs = get_similar_article_objects(obj.embedding_data, obj.id, count=5)
                return SimilarArticleSerializer(similar_objs, many=True, context=self.context).data
            except Exception:
                pass
        return []


class CommentSerializer(serializers.ModelSerializer):
    """سریالایزر درختی کامنت‌های تایید شده برای نمایش در فرانت‌اند"""
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['id', 'name', 'text', 'created_at', 'likes_count', 'replies']

    def get_replies(self, obj):
        # واکشی بازگشتی پاسخ‌های تایید شده
        approved_replies = obj.replies.filter(status=Comment.CommentStatus.APPROVED).order_by('created_at')
        return CommentSerializer(approved_replies, many=True, context=self.context).data


class CommentSubmitSerializer(serializers.ModelSerializer):
    """سریالایزر اعتبارسنجی ورودی نظرات جدید ثبت شده توسط کاربران"""

    class Meta:
        model = Comment
        fields = ['parent', 'name', 'email', 'text']

    def validate_text(self, value):
        if not value or len(value.strip()) < 5:
            raise serializers.ValidationError("متن دیدگاه باید حداقل شامل ۵ کاراکتر باشد.")
        return value
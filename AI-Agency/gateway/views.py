import logging
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, CreateAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from contents.models import Content, Category, Tag
from accounts.models import Comment
from gateway.serializers import (
    ContentListSerializer,
    ContentDetailSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    ContentTagSerializer,
    CommentSerializer,
    CommentSubmitSerializer
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# متدهای کمکی و بازگشتی
# ────────────────────────────────────────────────────────────────

def get_all_subcategory_ids(category: Category) -> list:
    """
    دریافت شناسه تمامی زیردسته‌ها به صورت بازگشتی.
    برای فیلتر کردن مقالاتی که متعلق به یک دسته یا فرزندان آن هستند.
    """
    sub_ids = [category.id]
    for child in category.children.filter(is_active=True):
        sub_ids.extend(get_all_subcategory_ids(child))
    return sub_ids


# ────────────────────────────────────────────────────────────────
# کلاس‌های صفحه‌بندی اختصاصی
# ────────────────────────────────────────────────────────────────

class GatewayStandardPagination(PageNumberPagination):
    """تنظیمات صفحه‌بندی استاندارد برای دریافت لیست مقالات"""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


# ────────────────────────────────────────────────────────────────
# کلاس‌های پردازشی ای‌پی‌آی (Views Implementation)
# ────────────────────────────────────────────────────────────────

class BreakingNewsListView(APIView):
    """ای‌پی‌آی اختصاصی و سبک دریافت اخبار فوری جهت بهینه‌سازی سرعت فرانت‌آسترو"""

    def get(self, request, *args, **kwargs):
        breaking_news = Content.objects.filter(
            status=Content.StatusChoices.PUBLISHED,
            importance=Content.ImportanceChoices.URGENT
        ).order_by('-publish_date', '-id')[:5]
        serializer = ContentListSerializer(breaking_news, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class HomepageAggregateView(APIView):
    """ای‌پی‌آی جامع تجمیع‌کننده صفحه اصلی - بهینه‌سازی شده بدون بارگذاری اخبار فوری و درخت دسته‌بندی‌ها"""

    # noinspection PyMethodMayBeStatic
    def get(self, request, *args, **kwargs):
        # ۱. آخرین مقالات و اخبار منتشر شده معمولی
        latest_news = Content.objects.filter(
            status=Content.StatusChoices.PUBLISHED
        ).order_by('-publish_date', '-id')[:10]

        # ۲. پربازدیدترین مقالات منتشر شده
        most_viewed = Content.objects.filter(
            status=Content.StatusChoices.PUBLISHED
        ).order_by('-views_count', '-id')[:10]

        # ۳. محبوب‌ترین برچسب‌های سیستم بر اساس بیشترین بازدید
        popular_tags = Tag.objects.all().order_by('-views_count', '-id')[:15]

        # ۴. دسته‌بندی‌های برتر به همراه مقالات پربازدید زیرمجموعه‌شان
        popular_cats_data = []
        top_categories = Category.objects.filter(is_active=True).order_by('-views_count', 'order')[:5]
        for cat in top_categories:
            all_sub_ids = get_all_subcategory_ids(cat)
            cat_articles = Content.objects.filter(
                category__id__in=all_sub_ids,
                status=Content.StatusChoices.PUBLISHED
            ).distinct().order_by('-views_count', '-id')[:4]

            popular_cats_data.append({
                "category_id": cat.id,
                "category_name": cat.name,
                "category_slug": cat.slug,
                "articles": ContentListSerializer(cat_articles, many=True, context={'request': request}).data
            })

        # سریالایز کردن ساختارها
        latest_serializer = ContentListSerializer(latest_news, many=True, context={'request': request})
        most_viewed_serializer = ContentListSerializer(most_viewed, many=True, context={'request': request})
        tags_serializer = ContentTagSerializer(popular_tags, many=True, context={'request': request})

        return Response({
            "latest_news": latest_serializer.data,
            "most_viewed": most_viewed_serializer.data,
            "popular_tags": tags_serializer.data,
            "popular_categories_articles": popular_cats_data
        }, status=status.HTTP_200_OK)


class SmartViewCounterView(APIView):
    """به‌روزرسانی اتمیک آمار بازدید مقاله، دسته‌بندی‌ها و تگ‌های مرتبط"""

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk, *args, **kwargs):
        try:
            with transaction.atomic():
                # قفل کردن رکورد جهت تراکنش همزمان ایمن
                content = Content.objects.select_for_update().get(pk=pk, status=Content.StatusChoices.PUBLISHED)

                # ۱. افزایش بازدید مقاله اصلی
                Content.objects.filter(pk=pk).update(views_count=F('views_count') + 1)

                # ۲. افزایش بازدید دسته‌بندی‌های والد و متصل
                category_ids = list(content.category.values_list('id', flat=True))
                if category_ids:
                    Category.objects.filter(id__in=category_ids).update(views_count=F('views_count') + 1)

                # ۳. افزایش بازدید برچسب‌های سفارشی متصل با کلید خارجی مستقیم و بومی دیتابیس
                tag_ids = list(content.tags.values_list('id', flat=True))
                if tag_ids:
                    Tag.objects.filter(id__in=tag_ids).update(views_count=F('views_count') + 1)

                content.refresh_from_db(fields=['views_count'])

                return Response({
                    "status": "success",
                    "article_id": pk,
                    "updated_views": {
                        "article": content.views_count,
                        "categories_updated_count": len(category_ids),
                        "tags_updated_count": len(tag_ids)
                    }
                }, status=status.HTTP_200_OK)

        except Content.DoesNotExist:
            return Response({"error": "محتوای منتشر شده با این شناسه یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in SmartViewCounterView for pk {pk}: {e}", exc_info=True)
            return Response({"error": "خطا در پردازش ثبت آمار بازدید."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LikeArticleView(APIView):
    """افزایش اتمیک تعداد پسندها (Likes) بدون تداخل تراکنشی"""

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk, *args, **kwargs):
        content = get_object_or_404(Content, pk=pk, status=Content.StatusChoices.PUBLISHED)
        Content.objects.filter(pk=pk).update(likes_count=F('likes_count') + 1)
        content.refresh_from_db(fields=['likes_count'])
        return Response({
            "status": "success",
            "article_id": pk,
            "likes_count": content.likes_count
        }, status=status.HTTP_200_OK)


class ShareArticleView(APIView):
    """افزایش اتمیک آمار به اشتراک‌گذاری"""

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk, *args, **kwargs):
        content = get_object_or_404(Content, pk=pk, status=Content.StatusChoices.PUBLISHED)
        Content.objects.filter(pk=pk).update(share_count=F('share_count') + 1)
        content.refresh_from_db(fields=['share_count'])
        return Response({
            "status": "success",
            "article_id": pk,
            "share_count": content.share_count
        }, status=status.HTTP_200_OK)


class GetCommentsView(ListAPIView):
    """دریافت نظرات تایید شده سطح اول (بدون والد) به همراه پاسخ‌های متصل به آن‌ها"""
    serializer_class = CommentSerializer

    def get_queryset(self):
        article_id = self.kwargs.get('pk')
        return Comment.objects.filter(
            content_id=article_id,
            status=Comment.CommentStatus.APPROVED,
            parent=None
        ).order_by('created_at')


class SubmitCommentView(CreateAPIView):
    """ثبت دیدگاه جدید برای مقاله با وضعیت اولیه در حال بررسی"""
    serializer_class = CommentSubmitSerializer

    def perform_create(self, serializer):
        article_pk = self.kwargs.get('pk')
        article = get_object_or_404(Content, pk=article_pk, status=Content.StatusChoices.PUBLISHED)
        serializer.save(content=article, status=Comment.CommentStatus.UNDER_REVIEW)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({
            "status": "success",
            "message": "دیدگاه شما با موفقیت ثبت شد و پس از بررسی و تایید ناظران منتشر خواهد شد."
        }, status=status.HTTP_201_CREATED)


class LikeCommentView(APIView):
    """افزایش اتمیک تعداد پسندهای دیدگاه (Comment Likes)"""

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk, *args, **kwargs):
        comment = get_object_or_404(Comment, pk=pk)
        Comment.objects.filter(pk=pk).update(likes_count=F('likes_count') + 1)
        comment.refresh_from_db(fields=['likes_count'])
        return Response({
            "status": "success",
            "comment_id": pk,
            "likes_count": comment.likes_count
        }, status=status.HTTP_200_OK)


class KeywordSearchView(ListAPIView):
    """جستجو و فیلتر پیشرفته مقالات به همراه صفحه‌بندی هوشمند"""
    serializer_class = ContentListSerializer
    pagination_class = GatewayStandardPagination

    def get_queryset(self):
        queryset = Content.objects.filter(status=Content.StatusChoices.PUBLISHED)

        # ۱. فیلتر بر اساس تگ (اختیاری) - با دقت و پرفورمنس بسیار بالا و بومی
        tag_param = self.request.GET.get('tag', '').strip()
        if tag_param:
            queryset = queryset.filter(
                Q(tags__slug__iexact=tag_param) | Q(tags__name__iexact=tag_param)
            )

        # ۲. فیلتر متنی بر اساس فیلد q (اختیاری)
        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(summary__icontains=query) |
                Q(content__icontains=query)
            )

        # ۳. فیلتر بازگشتی دسته‌بندی بر اساس اسلاگ (اختیاری)
        category_slug = self.request.GET.get('category', '').strip()
        if category_slug:
            try:
                category = Category.objects.get(slug=category_slug, is_active=True)
                all_sub_ids = get_all_subcategory_ids(category)
                queryset = queryset.filter(category__id__in=all_sub_ids)
            except Category.DoesNotExist:
                queryset = queryset.none()

        # ۴. فیلتر بازه زمانی (اختیاری)
        time_range = self.request.GET.get('time_range', '').strip()
        now = timezone.now()
        if time_range:
            if time_range == 'day':
                queryset = queryset.filter(publish_date__gte=now - timedelta(days=1))
            elif time_range == 'week':
                queryset = queryset.filter(publish_date__gte=now - timedelta(days=7))
            elif time_range == 'month':
                queryset = queryset.filter(publish_date__gte=now - timedelta(days=30))
            elif time_range == 'year':
                queryset = queryset.filter(publish_date__gte=now - timedelta(days=365))
        else:
            # فیلتر تاریخ به صورت داینامیک و بازه‌ای
            start_date = self.request.GET.get('start_date', '').strip()
            end_date = self.request.GET.get('end_date', '').strip()
            if start_date:
                queryset = queryset.filter(publish_date__date__gte=start_date)
            if end_date:
                queryset = queryset.filter(publish_date__date__lte=end_date)

        # ۵. مرتب‌سازی پویا بر اساس نوع فیلتر ارسالی
        sort_by = self.request.GET.get('sort_by', '').strip()
        if sort_by == 'popular':
            queryset = queryset.order_by('-views_count', '-id')
        elif sort_by == 'likes':
            queryset = queryset.order_by('-likes_count', '-id')
        else:
            # مرتب‌سازی پیش‌فرض بر اساس آخرین تاریخ انتشار
            queryset = queryset.order_by('-publish_date', '-id')

        return queryset.distinct()


class ArticleDetailView(RetrieveAPIView):
    """ای‌پی‌آی جزئیات دقیق خبر با ساختار بهینه برای رندر کش‌شدنی در Astro CDN"""
    queryset = Content.objects.filter(status=Content.StatusChoices.PUBLISHED)
    serializer_class = ContentDetailSerializer
    lookup_field = 'slug'


class ShortCodeResolutionView(APIView):
    """تبدیل و اعتبارسنجی کدهای کوتاه فرانت‌اند به ساختار غنی مقاله متناظر"""

    # noinspection PyMethodMayBeStatic
    def get(self, request, short_code, *args, **kwargs):
        try:
            content = Content.objects.get(short_code=short_code, status=Content.StatusChoices.PUBLISHED)
            return Response({
                "id": content.id,
                "title": content.title,
                "slug": content.slug,
                "summary": content.summary,
                "reading_time": content.reading_time,
                "publish_date": content.publish_date,
                "views_count": content.views_count,
                "likes_count": content.likes_count,
                "canonical_url": content.canonical_url
            }, status=status.HTTP_200_OK)
        except Content.DoesNotExist:
            return Response({"error": "کد کوتاه مورد نظر معتبر نمی‌باشد."}, status=status.HTTP_404_NOT_FOUND)


class CategoryArticlesView(APIView):
    """دریافت مقالات یک دسته و فرزندان بازگشتی آن به همراه خروجی زیردسته‌های سطح اول"""

    # noinspection PyMethodMayBeStatic
    def get(self, request, category_slug, *args, **kwargs):
        try:
            # ۱. دریافت دسته‌بندی جاری
            category = Category.objects.get(slug=category_slug, is_active=True)

            # ۲. دریافت فرزندان مستقیم (بدون نوه‌ها) برای ابزار ناوبری فرانت‌اند
            child_categories = category.children.filter(is_active=True).order_by('order', 'name')
            child_serializer = CategorySerializer(child_categories, many=True, context={'request': request})

            # ۳. دریافت تمام شناسه‌های درخت زیرمجموعه به صورت بازگشتی جهت فیلتر جامع مقالات
            all_sub_ids = get_all_subcategory_ids(category)

            # ۴. فیلتر کل مقالات منتشر شده در این زنجیره
            articles = Content.objects.filter(
                category__id__in=all_sub_ids,
                status=Content.StatusChoices.PUBLISHED
            ).distinct().order_by('-publish_date', '-id')

            # ۵. اعمال صفحه‌بندی استاندارد جامع
            paginator = GatewayStandardPagination()
            paginated_queryset = paginator.paginate_queryset(articles, request, view=self)

            if paginated_queryset is not None:
                serializer = ContentListSerializer(paginated_queryset, many=True, context={'request': request})
                paginated_response_data = paginator.get_paginated_response(serializer.data).data
            else:
                serializer = ContentListSerializer(articles, many=True, context={'request': request})
                paginated_response_data = {"results": serializer.data}

            return Response({
                "category_info": CategorySerializer(category, context={'request': request}).data,
                "child_categories": child_serializer.data,
                "articles": paginated_response_data
            }, status=status.HTTP_200_OK)

        except Category.DoesNotExist:
            return Response({"error": "دسته‌بندی مورد نظر فعال یا موجود نمی‌باشد."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in CategoryArticlesView for {category_slug}: {e}", exc_info=True)
            return Response({"error": "خطا در پردازش اطلاعات دسته‌بندی."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CategoryListView(ListAPIView):
    """دریافت درخت ساختاریافته تمامی دسته‌بندی‌های فعال سیستم با ساختار بازگشتی"""
    serializer_class = CategoryTreeSerializer

    def get_queryset(self):
        # بازگرداندن ریشه‌های درخت به همراه پیش‌فرض در بر گرفتن کل ساختار فرزندان
        return Category.objects.filter(is_active=True, parent=None).order_by('order', 'name')
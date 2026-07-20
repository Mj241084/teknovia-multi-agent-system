from django.urls import path
from gateway.views import (
    HomepageAggregateView,
    BreakingNewsListView,
    SmartViewCounterView,
    LikeArticleView,
    ShareArticleView,
    GetCommentsView,
    SubmitCommentView,
    LikeCommentView,
    KeywordSearchView,
    ArticleDetailView,
    ShortCodeResolutionView,
    CategoryArticlesView,
    CategoryListView
)

app_name = 'gateway'

urlpatterns = [
    # تجمیع‌کننده اختصاصی صفحه اول (سبک‌سازی شده)
    path('homepage/', HomepageAggregateView.as_view(), name='homepage'),

    # وب‌سرویس مجزا، فوق‌العاده سریع و کش‌شدنی اخبار فوری
    path('breaking-news/', BreakingNewsListView.as_view(), name='breaking-news'),

    # دریافت لیست و درخت کامل دسته‌بندی‌ها
    path('categories/', CategoryListView.as_view(), name='category-list'),

    # دریافت مقالات دسته و فرزندان آن به صورت بازگشتی
    path('categories/<str:category_slug>/articles/', CategoryArticlesView.as_view(), name='category-articles'),

    # تحلیل و جزئیات مقالات
    path('articles/search/', KeywordSearchView.as_view(), name='article-search'),
    path('articles/<str:slug>/', ArticleDetailView.as_view(), name='article-detail'),
    path('s/<str:short_code>/', ShortCodeResolutionView.as_view(), name='short-code-resolve'),

    # ثبت رخدادهای تعاملی کلاینت (بازدید، پسند، اشتراک)
    path('articles/<int:pk>/view/', SmartViewCounterView.as_view(), name='article-view'),
    path('articles/<int:pk>/like/', LikeArticleView.as_view(), name='article-like'),
    path('articles/<int:pk>/share/', ShareArticleView.as_view(), name='article-share'),

    # سیستم ثبت، دریافت و لایک نظرات
    path('articles/<int:pk>/comments/', GetCommentsView.as_view(), name='article-comments'),
    path('articles/<int:pk>/comments/submit/', SubmitCommentView.as_view(), name='article-comments-submit'),
    path('comments/<int:pk>/like/', LikeCommentView.as_view(), name='comment-like'),
]
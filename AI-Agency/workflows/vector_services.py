import os
import requests
import logging
import numpy as np
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from contents.models import Content
from workflows.models import ReceivedMessages
from django.conf import settings
logger = logging.getLogger(__name__)
load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")
# راه‌اندازی امبدینگ گوگل با لنگ‌چین (Gemini Embedding 2 با ابعاد 768)
embeddings_model = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-2",
    output_dimensionality=768,
)

# تغییر آدرس از لوکال‌هاست به سرویس داکر برای برقراری ارتباط کانتینرها
FASTAPI_BASE_URL = "http://vector_fastapi:8000"


def generate_text_embedding(text: str) -> list:
    """تولید وکتور با استفاده از LangChain GoogleEmbeddings"""
    if not text or not text.strip():
        return []
    try:
        return embeddings_model.embed_query(text.strip())
    except Exception as e:
        logger.error(f"خطا در تولید امبدینگ: {e}", exc_info=True)
        return []


def search_index_by_vector(collection_name: str, vector: list, top_k: int) -> list:
    """جستجوی برداری مستقیم در FastAPI"""
    if not vector:
        return []
    url = f"{FASTAPI_BASE_URL}/collections/{collection_name}/search"
    payload = {"vector": vector, "top_k": top_k}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get("results", [])
        return []
    except Exception as e:
        logger.error(f"خطا در ارتباط با FastAPI (Search): {e}")
        return []


# ────────────────────────────────────────────────────────────────
# تابع برای بررسی تکراری‌ها توسط ایجنت
# ────────────────────────────────────────────────────────────────
# workflows/vector_services.py

def check_text_for_potential_duplicates(text: str, collection_name: str, top_k: int = 3,
                                        threshold: float = 0.65, high_threshold: float = 0.90,
                                        embed=None) -> dict:
    """
    بررسی هوشمند تکراری بودن به همراه تعیین حد بالا برای حذف سریع بدون نیاز به هوش مصنوعی
    """
    vector = generate_text_embedding(text) if embed is None else embed
    if not vector:
        return {"action": "error", "message": "Failed to generate embedding"}

    results = search_index_by_vector(collection_name, vector, top_k=top_k)
    potential_duplicates = []
    has_high_confidence_duplicate = False

    for match in results:
        similarity_score = match["similarity_score"]

        # اگر شباهت از مرز تعیین شده برای تایید قطعی تکراری بودن فراتر رود
        if similarity_score >= high_threshold:
            has_high_confidence_duplicate = True

        if similarity_score >= threshold:
            matched_django_id = match["django_id"]
            matched_text = ""
            source_type = ""

            try:
                if collection_name == settings.CONTENTS:
                    article = Content.objects.get(id=matched_django_id)
                    matched_text = f"Title: {article.title}\nDescription: {article.content[:500]}"
                    source_type = "Published Article"

                elif collection_name == settings.RECEIVED:
                    msg = ReceivedMessages.objects.get(id=matched_django_id)
                    matched_text = msg.raw_text
                    source_type = "In-Queue Message"

                potential_duplicates.append({
                    "django_id": matched_django_id,
                    "similarity_score": round(similarity_score, 4),
                    "source_type": source_type,
                    "content_text": matched_text
                })
            except Exception as e:
                logger.error(f"Error fetching record {matched_django_id} from Django DB: {e}")
                continue

    # ۱. اگر شباهت بسیار بالا یافت شد، نیازی به تحلیل هوش مصنوعی نیست
    if has_high_confidence_duplicate:
        return {
            "action": "duplicate_detected",
            "message": f"Highly confident duplicate detected with similarity score >= {high_threshold}."
        }

    # ۲. اگر شباهت در محدوده خاکستری بود، برای تصمیم‌گیری فرستاده می‌شود
    if potential_duplicates:
        return {
            "action": "agent_decision_required",
            "matches_found": len(potential_duplicates),
            "potential_duplicates": potential_duplicates,
            "instruction": "Analyze the potential duplicates."
        }

    # ۳. اگر هیچ شباهتی بالای حد آستانه نبود
    return {
        "action": "proceed",
        "message": f"No items found matching the similarity threshold of {threshold}. Unique content."
    }


def get_similar_article_objects(embedding_data_bytes, current_django_id: int, count: int = 5) -> list:
    """
    دریافت اشیای کامل دیتابیس (Django Objects) برای مقالات مشابه.
    مفید برای ساخت بخش پیشنهاد مقاله.
    """
    if not embedding_data_bytes:
        return []

    vector = np.frombuffer(embedding_data_bytes, dtype=np.float32).tolist()
    raw_results = search_index_by_vector("contents", vector, top_k=count + 1)

    similar_articles = []
    for item in raw_results:
        target_id = item["django_id"]
        if target_id == current_django_id:
            continue

        # دریافت مستقیم آبجکت جنگو برای استفاده در تمپلت یا سیستم پیشنهاد
        article = Content.objects.filter(id=target_id).first()
        if article:
            # امتیاز شباهت را هم موقتاً به آبجکت می‌چسبانیم تا در صورت نیاز در فرانت نمایش دهید
            article.similarity_score = item["similarity_score"]
            similar_articles.append(article)

    return similar_articles[:count]


def add_document_to_vector_index(collection_name: str, django_id: int, vector: list) -> int | None:
    """
    درج مستقیم بردار در فست‌ای‌پیاآی.
    در صورت موفقیت، شناسه اختصاصی بردار (external_id) را برمی‌گرداند.
    """
    if not vector:
        return None

    # همگام با مسیر تعریف شده در FastAPI شما
    url = f"{FASTAPI_BASE_URL}/collections/{collection_name}/add"

    # مطابق با اسکیما VectorInsert تعریف شده در فست‌ای‌پی‌آی
    payload = {
        "django_id": django_id,
        "vector": vector
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            return res_data.get("external_id")
        return None
    except Exception as e:
        logger.error(f"خطا در ارتباط با FastAPI برای درج سند در ایندکس برداری: {e}")
        return None
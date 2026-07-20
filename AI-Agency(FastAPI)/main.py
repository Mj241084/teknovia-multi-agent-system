import os
import json
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from turbovec import TurboQuantIndex
app = FastAPI(title="TurboVec Multi-Collection Service")

# پوشه اصلی ذخیره‌سازی فایل‌ها
STORAGE_DIR = "vector_storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

# ابعاد پیشنهادی گوگل برای Gemini Embedding 2
DIMENSION = 768

# رجیستری داخلی برای نگهداری کالکشن‌های لود شده در حافظه رم
# { "contents": {"index": ..., "id_map": ...}, "received_messages": {...} }
_LOADED_COLLECTIONS: Dict[str, Dict[str, Any]] = {}


def get_collection(collection_name: str):
    """لود کردن دینامیک کالکشن از دیسک یا ساخت کالکشن جدید در صورت عدم وجود"""
    if collection_name in _LOADED_COLLECTIONS:
        return _LOADED_COLLECTIONS[collection_name]

    # ساخت دایرکتوری اختصاصی برای این کالکشن
    col_dir = os.path.join(STORAGE_DIR, collection_name)
    os.makedirs(col_dir, exist_ok=True)

    index_file = os.path.join(col_dir, "index.tvim")
    mapping_file = os.path.join(col_dir, "mapping.json")

    if os.path.exists(index_file) and os.path.exists(mapping_file):
        index = TurboQuantIndex.load(index_file)
        with open(mapping_file, "r") as f:
            id_map = json.load(f)
        print(f"🟢 Collection '{collection_name}' loaded from disk.")
    else:
        index = TurboQuantIndex(dim=DIMENSION, bit_width=4)
        id_map = {}
        print(f"🆕 Initialized new empty collection: '{collection_name}'")

    _LOADED_COLLECTIONS[collection_name] = {"index": index, "id_map": id_map}
    return _LOADED_COLLECTIONS[collection_name]


def save_collection(collection_name: str, index, id_map):
    """ذخیره وضعیت کالکشن روی دیسک"""
    col_dir = os.path.join(STORAGE_DIR, collection_name)
    index_file = os.path.join(col_dir, "index.tvim")
    mapping_file = os.path.join(col_dir, "mapping.json")

    index.write(index_file)
    with open(mapping_file, "w") as f:
        json.dump(id_map, f)


# --- اسکیماهای Pydantic ---
class VectorInsert(BaseModel):
    django_id: int
    vector: List[float]


class VectorSearch(BaseModel):
    vector: List[float]
    top_k: int = 5


# --- اندپوینت‌ها ---

@app.post("/collections/{collection_name}/add")
async def add_vector(collection_name: str, data: VectorInsert):
    col = get_collection(collection_name)
    index = col["index"]
    id_map = col["id_map"]

    try:
        vec = np.array([data.vector], dtype=np.float32)

        # شناسه اختصاصی بردار (Index داخلی TurboVec)
        external_id = len(id_map)

        # اضافه کردن به وکتور ایندکس
        index.add(vec)

        # ذخیره نگاشت: کلید آیدی توربووک -> مقدار آیدی دیتابیس جنگو
        id_map[str(external_id)] = data.django_id

        # پایدارسازی روی دیسک
        save_collection(collection_name, index, id_map)

        return {
            "status": "success",
            "collection": collection_name,
            "external_id": external_id,
            "django_id": data.django_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/search")
async def search_vector(collection_name: str, data: VectorSearch):
    col = get_collection(collection_name)
    index = col["index"]
    id_map = col["id_map"]

    try:
        query_vec = np.array([data.vector], dtype=np.float32)
        scores, indices = index.search(query_vec, k=data.top_k)

        results = []
        for score, internal_idx in zip(scores[0], indices[0]):
            str_idx = str(internal_idx)
            if str_idx in id_map:
                results.append({
                    "django_id": id_map[str_idx],
                    "external_id": int(internal_idx),
                    "similarity_score": float(score)
                })
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
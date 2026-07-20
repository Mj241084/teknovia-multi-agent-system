# workflows/graph_workflow.py

import logging
from langgraph.graph import StateGraph, START, END
from workflows.models import ReceivedMessages

# ایمپورت کردن نودها و مدل استیت شما
from workflows.proccessor import (
    MessageStates,
    observer_node,
    checker_node,
    fetcher_node,
    analyzer_node,
    image_editor_node,  # ایمپورت نود جدید ادیتور هوشمند تصویر
    saver_node
)

logger = logging.getLogger(__name__)

def get_graph_app():
    """
    ثبت، ساختاربندی و کامپایل گراف لنگ‌چین
    """
    # تعریف استیت گراف بر اساس مدل کلاس Pydantic
    workflow = StateGraph(MessageStates)

    # ثبت تمامی نودهای توسعه داده شده در زنجیره
    workflow.add_node("observer", observer_node)
    workflow.add_node("checker", checker_node)
    workflow.add_node("fetcher", fetcher_node)
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("image_editor", image_editor_node)  # ثبت نود جدید ادیتور
    workflow.add_node("saver", saver_node)

    # تعریف لبه‌ی ورودی گراف به اولین نود (observer)
    workflow.add_edge(START, "observer")

    # کامپایل نهایی گراف
    return workflow.compile()
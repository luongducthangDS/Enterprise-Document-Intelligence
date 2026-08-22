"""Knowledge Lookup Node for LangGraph Agent.

Truy vấn đồ thị tri thức có cấu trúc TRƯỚC RAG retrieval:
- Nếu câu hỏi có thể giải quyết tất định bằng quy tắc chính sách đã phê duyệt (APPROVED) và quan hệ liên kết (MODIFIES / SUPERSEDES),
- Trả về câu trả lời chính xác 100%, không bị ảnh hưởng bởi hallucinations hay semantic drift của vector search.
- Nếu không có quy tắc phù hợp, chuyển tiếp sang RAG retrieval thông thường.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from src.agents.state import AgentState
from src.knowledge.database import get_session
from src.knowledge.resolver import (
    DeterministicPolicyResolver,
    PolicyQueryRequest,
    verbalize_policy_resolution,
)

logger = logging.getLogger(__name__)

_HOTEL_ALLOWANCE_PATTERNS = re.compile(
    r"(?:khách sạn|khach san|lưu trú|luu tru|công tác phí|cong tac phi|định mức phòng|dinh muc phong|hạn mức|han muc)",
    re.IGNORECASE,
)


def _extract_location_from_query(query: str) -> str:
    q = query.lower()
    if "hà nội" in q or "ha noi" in q or "hn" in q:
        return "HANOI"
    if "hồ chí minh" in q or "ho chi minh" in q or "tp.hcm" in q or "tphcm" in q or "sài gòn" in q or "sai gon" in q or "hcm" in q:
        return "HO_CHI_MINH_CITY"
    if "đà nẵng" in q or "da nang" in q:
        return "DA_NANG"
    if "hải phòng" in q or "hai phong" in q:
        return "HAI_PHONG"
    if "cần thơ" in q or "can tho" in q:
        return "CAN_THO"
    return "HO_CHI_MINH_CITY"  # default special urban probe


def _extract_role_from_query(query: str) -> str:
    q = query.lower()
    if "lãnh đạo" in q or "lanh dao" in q or "giám đốc" in q or "giam doc" in q or "director" in q:
        return "DIRECTOR"
    if "quản lý" in q or "quan ly" in q or "trưởng phòng" in q or "manager" in q:
        return "MANAGER"
    if "chuyên viên" in q or "chuyen vien" in q or "specialist" in q:
        return "SPECIALIST"
    return "STAFF"


async def knowledge_lookup_node(state: AgentState) -> dict[str, Any]:
    """Node kiểm tra đồ thị tri thức cấu trúc trước khi thực hiện vector retrieval."""
    query = state.get("condensed_query") or state.get("query") or ""
    tenant_id = state.get("tenant_id") or "nexatech"

    # Kiểm tra nếu câu hỏi liên quan đến định mức công tác phí / khách sạn
    if not _HOTEL_ALLOWANCE_PATTERNS.search(query):
        return {"structured_knowledge": None, "skip_retrieval": False}

    loc = _extract_location_from_query(query)
    role = _extract_role_from_query(query)

    try:
        with get_session() as session:
            resolver = DeterministicPolicyResolver(session)
            req = PolicyQueryRequest(
                tenant_id=tenant_id,
                subject="hotel_allowance",
                location=loc,
                role=role,
                target_date_ymd=20260901,  # Thời điểm hiện tại giả định
            )
            res = resolver.resolve_hotel_allowance(req)
            if res and res.resolved:
                verbalized = verbalize_policy_resolution(res)
                return {
                    "structured_knowledge": {
                        "resolved": True,
                        "subject": res.subject,
                        "value_numeric": res.value_numeric,
                        "currency": res.currency,
                        "unit": res.unit,
                        "answer": verbalized,
                        "document": res.resolved_by_document,
                        "authority": res.resolved_by_authority,
                        "is_modified": res.is_modified,
                    },
                    "skip_retrieval": True,
                }
    except Exception as e:
        logger.debug("Knowledge lookup bypass or failed: %s", e)

    return {"structured_knowledge": None, "skip_retrieval": False}

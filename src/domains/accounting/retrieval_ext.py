"""Retrieval extensions cho domain Phòng Kế toán & Tài chính.

Bao gồm:
  - G1: Nhận diện query kế toán (_is_accounting_query)
  - G2: Bộ từ điển mở rộng Query Expansion (_expand_accounting_query)
  - G3: Dynamic Top-K Expansion (_get_accounting_top_k)
"""
from __future__ import annotations

import re

# ─── G1: Nhận diện query kế toán ─────────────────────────────────────────────
_ACCOUNTING_KEYWORD_PATTERN = re.compile(
    r"\b(?:tạm ứng|hoàn ứng|duyệt chi|mua sắm|báo giá|hóa đơn|kế toán"
    r"|thuế|gtgt|vat|po|pr|cba|avl|tiền mặt|chuyển khoản|thanh toán"
    r"|ngân sách|chi phí|quyết toán|phiếu chi|phiếu thu|sop-tckt|sop-ms"
    r"|13/qđ-abc|13-qd-abc|qc-ltk|bbgn|đntt|dntt|chứng từ)\b",
    re.IGNORECASE,
)
_ACCOUNTING_CATEGORY_PREFIX = ("accounting", "finance", "procurement", "internal_expense", "payroll_and_compensation", "advance_and_payment")


def _is_accounting_query(query: str, category: str | None = None) -> bool:
    """Xác định xem truy vấn có thuộc phạm vi Kế toán / Tài chính / Mua sắm không."""
    if category:
        cat_lower = category.lower()
        if any(cat_lower.startswith(p) for p in _ACCOUNTING_CATEGORY_PREFIX):
            return True
    return bool(_ACCOUNTING_KEYWORD_PATTERN.search(query))


# ─── G2: Query Expansion ─────────────────────────────────────────────────────
_ACCOUNTING_EXPANSION_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\b(?:tách đơn|chia nhỏ|lách luật|né hạn mức)\b", re.IGNORECASE),
        "nghiêm cấm hành vi cố ý chia nhỏ khoản chi tách hợp đồng thẩm quyền phê duyệt",
    ),
    (
        re.compile(
            r"\b(?:hóa đơn giấy|hóa đơn viết tay|hóa đơn không hợp lệ|không tra cứu được)\b",
            re.IGNORECASE,
        ),
        "hóa đơn GTGT điện tử hợp pháp hợp lệ tra cứu hệ thống Tổng cục Thuế từ chối thanh toán",
    ),
    (
        re.compile(r"\b(?:duyệt chi|ai duyệt|thẩm quyền ký|hạn mức duyệt)\b", re.IGNORECASE),
        "thẩm quyền phê duyệt hạn mức duyệt chi Giám đốc Trưởng phòng Kế toán trưởng",
    ),
    (
        re.compile(r"\b(?:mua sắm khẩn cấp|mua gấp|sự cố đột xuất)\b", re.IGNORECASE),
        "mua sắm khẩn cấp bất khả kháng gián đoạn kinh doanh bổ sung hồ sơ 48 giờ",
    ),
    (
        re.compile(
            r"\b(?:quá hạn hoàn ứng|chậm thanh toán tạm ứng|quên hoàn ứng)\b", re.IGNORECASE
        ),
        "thời hạn hoàn ứng quá hạn 15 ngày tự động khấu trừ vào lương",
    ),
]


def _expand_accounting_query(query: str) -> str:
    """Mở rộng từ đồng nghĩa và cụm từ quy chế đặc thù kế toán."""
    matched: list[str] = []
    for pattern, extra_terms in _ACCOUNTING_EXPANSION_RULES:
        if pattern.search(query):
            matched.append(extra_terms)
    if not matched:
        return query
    return f"{query}\nNgữ cảnh quy chế Kế toán: {' | '.join(matched)}"


# ─── G3: Dynamic Top-K Multi-source ──────────────────────────────────────────
_MULTI_DOC_PATTERN = re.compile(
    r"(?:giữa|và|với|đồng thời|đối chiếu|so sánh|theo cả).*?"
    r"(?:SOP|QĐ|QC|PO|PR|BC|Hóa đơn|Biên bản)"
    r"|(?:SOP|QĐ|QC)[\w\-]*.*?(?:và|với).*?(?:SOP|QĐ|QC)[\w\-]*",
    re.IGNORECASE,
)
ACCOUNTING_MULTI_DOC_TOP_K = 15


def _get_accounting_top_k(query: str, default_k: int) -> int:
    """Tự động mở rộng Top-K lên 15 nếu câu hỏi cần đối chiếu giữa nhiều văn bản."""
    if _MULTI_DOC_PATTERN.search(query):
        return max(default_k, ACCOUNTING_MULTI_DOC_TOP_K)
    return default_k


def is_accounting_request(state: dict) -> bool:
    """Kiểm tra xem request có thuộc phân hệ Kế toán không."""
    raw_query = state.get("rewritten_query") or state.get("condensed_query") or state.get("query", "")
    category = state.get("category")
    return _is_accounting_query(raw_query, category)


async def accounting_retrieval_node(state: dict) -> dict:
    """Node retrieval độc lập cho phân hệ Kế toán.

    Tách biệt 100% với retrieval_node gốc của HR:
    - Tự động áp dụng Query Expansion kế toán (G2)
    - Tự động áp dụng Dynamic Top-K (G3)
    - Tự động kích hoạt Hybrid Search (G1)
    - Kết nối Chroma Cloud (collection accounting_documents hoặc tenant_nexatech_knowledge)
    - Tái xếp hạng bằng Reranker (G7)
    """
    import asyncio
    from functools import partial
    from src.agents.nodes.retrieval import _aembed_query, _arerank, _collection, _provenance_filter, _to_chunk
    from src.config import get_settings
    from src.ingestion.indexer import get_chroma_client, get_collection
    from src.observability import llm_trace

    settings = get_settings()
    raw_query = state.get("rewritten_query") or state.get("condensed_query") or state.get("query", "")
    query = _expand_accounting_query(raw_query)
    effective_top_k = _get_accounting_top_k(raw_query, settings.retrieval_top_k)

    embedding = await _aembed_query(query)

    # Ưu tiên collection accounting_documents, fallback về collection mặc định
    client = get_chroma_client(settings)
    try:
        col = get_collection(client, "accounting_documents")
    except Exception:
        col = _collection()

    allowed_categories = state.get("allowed_categories")
    user_role = state.get("user_role")
    if not allowed_categories:
        if user_role == "admin":
            allowed_categories = ["GENERAL", "LEGAL", "DEPARTMENT", "EXTERNAL_REFERENCE"]
        else:
            allowed_categories = ["GENERAL"]
    where = _provenance_filter(settings, allowed_categories=allowed_categories)

    with llm_trace.Timer("vector_search", "chroma_cloud", n_results=effective_top_k):
        result = await asyncio.to_thread(
            partial(col.query, where=where) if where else col.query,
            query_embeddings=[embedding],
            n_results=effective_top_k,
        )

    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    chunk_map = {
        chunk_id: _to_chunk(chunk_id, text, meta, distance)
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances)
    }

    chunks = list(chunk_map.values())
    if settings.use_reranker and chunks:
        chunks = await _arerank(query, chunks)

    return {"retrieved_chunks": chunks}


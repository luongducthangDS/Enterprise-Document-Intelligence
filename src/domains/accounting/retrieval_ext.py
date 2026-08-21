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


def _to_accounting_chunk(chunk_id: str, text: str, meta: dict, distance: float) -> dict:
    """Chuyển đổi metadata Chroma thành RetrievedChunk chuẩn."""
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": meta.get("source_file", ""),
        "title": meta.get("title", ""),
        "department": str(meta.get("department") or "accounting"),
        "category": meta.get("category", ""),
        "is_official_policy": bool(meta.get("is_official_policy", True)),
        "source_type": str(meta.get("source_type") or "internal_policy"),
        "authority": str(meta.get("authority") or "tenant_official_policy"),
        "provenance": str(meta.get("provenance") or "internal_company"),
        "tenant": str(meta.get("tenant") or ""),
        "caveat": str(meta.get("caveat") or ""),
        "heading_path": str(meta.get("heading_path") or ""),
        "policy_status": str(meta.get("publication_status") or "active"),
        "page_start": meta.get("page_start"),
        "page_end": meta.get("page_end"),
        "sheet_start": meta.get("sheet_start"),
        "sheet_end": meta.get("sheet_end"),
        "distance": distance,
        "score": None,
    }


def _accounting_provenance_filter(settings, allowed_categories: list[str] | None = None) -> dict:
    """Bộ lọc quyền truy xuất chuẩn doanh nghiệp cho Kế toán."""
    from datetime import datetime, timezone
    try:
        from datetime import UTC
    except ImportError:
        UTC = timezone.utc
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
    categories = allowed_categories or ["GENERAL"]
    category_filter = (
        {"access_category": {"$in": categories}}
        if len(categories) > 1
        else {"access_category": {"$eq": categories[0]}}
    )
    return {
        "$and": [
            category_filter,
            {"publication_status": "active"},
            {"artifact_state": "frozen"},
            {"retrieval_enabled": True},
            {"effective_date_ymd": {"$lte": query_date_ymd}},
            {"expiry_date_ymd": {"$gte": query_date_ymd}},
        ]
    }


async def accounting_retrieval_node(state: dict) -> dict:
    """Node retrieval độc lập 100% cho phân hệ Kế toán.

    Tách biệt hoàn toàn với mọi hàm của HR trên develop:
    - Tự động áp dụng Query Expansion kế toán (G2)
    - Tự động áp dụng Dynamic Top-K (G3)
    - Tự động lọc metadata quyền truy cập Kế toán
    - Kết nối trực tiếp Chroma Cloud collection accounting_documents
    - Tái xếp hạng bằng Reranker (G7)
    """
    import asyncio
    from functools import partial
    from src.config import get_settings
    from src.ingestion.indexer import get_chroma_client, get_collection
    from src.observability import llm_trace
    from src.services.fpt_client import embed_batch, rerank

    settings = get_settings()
    raw_query = state.get("rewritten_query") or state.get("condensed_query") or state.get("query", "")
    query = _expand_accounting_query(raw_query)
    effective_top_k = _get_accounting_top_k(raw_query, settings.retrieval_top_k)

    # 1. Tính embedding câu hỏi
    with llm_trace.Timer("embedding", "fpt_cloud"):
        vectors = await asyncio.to_thread(
            embed_batch,
            [f"query: {query}"],
            model=settings.embedding_model,
            base_url=settings.fpt_base_url,
            api_key=settings.fpt_api_key,
        )
        embedding = vectors[0]

    # 2. Kết nối collection Kế toán trên Chroma Cloud
    client = get_chroma_client(settings)
    collection_name = "accounting_documents"
    try:
        col = get_collection(client, collection_name)
    except Exception:
        col = get_collection(client, settings.chroma_collection_name)

    allowed_categories = state.get("allowed_categories")
    user_role = state.get("user_role")
    if not allowed_categories:
        if user_role == "admin":
            allowed_categories = ["GENERAL", "LEGAL", "DEPARTMENT", "EXTERNAL_REFERENCE"]
        else:
            allowed_categories = ["GENERAL"]

    where = _accounting_provenance_filter(settings, allowed_categories=allowed_categories)

    # 3. Vector search
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
        chunk_id: _to_accounting_chunk(chunk_id, text, meta, distance)
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances)
    }

    chunks = list(chunk_map.values())

    # 4. Rerank
    if settings.use_reranker and chunks:
        try:
            ranked = await asyncio.to_thread(
                rerank,
                query,
                [c["text"] for c in chunks],
                model=settings.reranker_model,
                base_url=settings.fpt_base_url,
                api_key=settings.fpt_api_key,
                top_n=settings.rerank_top_k,
            )
            reranked = []
            for index, score in ranked:
                if 0 <= index < len(chunks):
                    chunk = chunks[index]
                    chunk["score"] = score
                    reranked.append(chunk)
            chunks = reranked[: settings.rerank_top_k]
        except Exception as e:
            print(f"[accounting_rerank] lỗi {type(e).__name__}: {e}")
            chunks = chunks[: settings.rerank_top_k]

    return {"retrieved_chunks": chunks}



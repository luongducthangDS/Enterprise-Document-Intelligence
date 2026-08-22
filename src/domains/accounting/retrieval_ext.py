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
        "owner": meta.get("owner", ""),
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


def _accounting_provenance_filter(settings, user_context) -> dict:
    """Registry corpus branch, below Chroma's 8-predicate quota."""
    from datetime import datetime, timezone
    try:
        from datetime import UTC
    except ImportError:
        UTC = timezone.utc
    from src.ingestion.metadata import DEMO_ONLY_PROVENANCE
    from src.security import get_authorization_engine

    allowed_files = get_authorization_engine().get_authorized_source_files(user_context)
    if not allowed_files:
        return {"source_file": "__NO_ACCESS__"}
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
    conditions = [
        {"source_file": {"$in": allowed_files}} if len(allowed_files) > 1 else {"source_file": allowed_files[0]},
        {"publication_status": "active"},
        {"artifact_state": "frozen"},
        {"retrieval_enabled": True},
        {"effective_date_ymd": {"$lte": query_date_ymd}},
        {"expiry_date_ymd": {"$gte": query_date_ymd}},
    ]
    if settings.data_mode == "production":
        conditions.append({"provenance": {"$nin": sorted(DEMO_ONLY_PROVENANCE)}})
    return {"$and": conditions}


def _accounting_retrieval_filters(settings, user_context) -> list[dict]:
    from datetime import datetime, timezone
    try:
        from datetime import UTC
    except ImportError:
        UTC = timezone.utc
    from src.security import runtime_upload_access_filters

    filters: list[dict] = []
    offline = _accounting_provenance_filter(settings, user_context)
    if offline != {"source_file": "__NO_ACCESS__"}:
        filters.append(offline)
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
    lifecycle = [
        {"publication_status": "active"},
        {"artifact_state": "frozen"},
        {"retrieval_enabled": True},
        {"effective_date_ymd": {"$lte": query_date_ymd}},
        {"expiry_date_ymd": {"$gte": query_date_ymd}},
    ]
    for access in runtime_upload_access_filters(user_context):
        access_conditions = access["$and"] if "$and" in access else [access]
        filters.append({"$and": [*access_conditions, *lifecycle]})
    return filters or [{"source_file": "__NO_ACCESS__"}]


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
    from src.ingestion.indexer import collection_name_for_department, get_chroma_client, get_collection
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

    # 2. Kết nối collection Kế toán tenant-scoped trên Chroma Cloud
    from src.security import UserContext
    user_context = UserContext.from_state(state)
    client = get_chroma_client(settings)
    collection_name = collection_name_for_department("Accounting", settings, user_context.tenant_id)
    # Dedicated domain collection is mandatory. Never fall back across domains.
    col = get_collection(client, collection_name)
    filters = _accounting_retrieval_filters(settings, user_context)

    # 3. Vector search: one quota-safe branch per access grant, then deduplicate.
    with llm_trace.Timer("vector_search", "chroma_cloud", n_results=effective_top_k):
        branch_results = await asyncio.gather(*[
            asyncio.to_thread(
                partial(col.query, where=where),
                query_embeddings=[embedding],
                n_results=effective_top_k,
            )
            for where in filters
        ])
        from src.agents.nodes.retrieval import _merge_query_results
        result = _merge_query_results(branch_results, effective_top_k)

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



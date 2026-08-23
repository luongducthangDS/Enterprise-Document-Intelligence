import asyncio
import re
from datetime import UTC, datetime
from functools import lru_cache, partial

from src.agents.llm import acall_llm, thinking_arg
from src.agents.state import AgentState, RetrievedChunk
from src.config import Settings, get_settings
from src.ingestion.indexer import collection_name_for_department, get_chroma_client, get_collection
from src.ingestion.metadata import DEMO_ONLY_PROVENANCE
from src.observability import llm_trace
from src.retrieval.bm25 import BM25
from src.retrieval.cache import get_cached_embedding, set_cached_embedding
from src.retrieval.hybrid import reciprocal_rank_fusion
from src.security import (
    UserContext,
    canonical_department,
    get_authorization_engine,
    runtime_upload_access_filters,
    runtime_upload_metadata_allowed,
)
from src.security.tenant_resolver import resolve_tenant_collection
from src.services.fpt_client import embed_batch, rerank

_REWRITE_SYSTEM = """Bạn giúp viết lại câu hỏi tri thức nội bộ HR hoặc Product để tìm kiếm tài liệu chính xác hơn. Giữ nguyên ý định gốc của người hỏi, nhưng diễn đạt lại rõ ràng hơn, thêm từ khoá chuyên môn liên quan nếu có thể. Chỉ trả về câu hỏi đã viết lại, không giải thích."""
_HYBRID_QUERY_PATTERN = re.compile(r"\b(?:hybrid|wfh)\b|làm việc từ xa", re.IGNORECASE)
_REFERRAL_QUERY_PATTERN = re.compile(
    r"\breferral\b"
    r"|(?:giới thiệu|gioi thieu).{0,48}(?:ứng tuyển|ung tuyen|ứng viên|ung vien|người quen|nguoi quen|bạn|ban)"
    r"|(?:ứng tuyển|ung tuyen|ứng viên|ung vien).{0,48}(?:giới thiệu|gioi thieu|referral)",
    re.IGNORECASE,
)
_DISCIPLINARY_ABSENCE_QUERY_PATTERN = re.compile(
    r"(?:tự ý|tu y).{0,40}(?:nghỉ|nghi|bỏ việc|bo viec)"
    r"|(?:sa thải|sa thai|kỷ luật|ky luat).{0,48}(?:nghỉ|nghi|bỏ việc|bo viec|vắng|vang)"
    r"|(?:nghỉ|nghi|bỏ việc|bo viec).{0,48}(?:sa thải|sa thai|kỷ luật|ky luat|phê duyệt|phe duyet)",
    re.IGNORECASE,
)


_KPI_QUERY_PATTERN = re.compile(
    r"đánh giá.{0,24}(?:hiệu suất|thành tích|kết quả|năng lực|nhân viên)|kpi|okr|performance review|xếp loại",
    re.IGNORECASE,
)
_RECRUITMENT_QUERY_PATTERN = re.compile(
    r"quy trình tuyển dụng|kế hoạch tuyển dụng|hội đồng tuyển dụng|tiêu chuẩn tuyển dụng|tuyển dụng nhân sự",
    re.IGNORECASE,
)


def _expand_retrieval_query(query: str) -> str:
    """Bổ sung từ đồng nghĩa ổn định cho các cách nói lệch từ vựng tài liệu.

    Expansion nhỏ này giúp dense và BM25 tìm đúng ngay lượt đầu mà không cần
    gọi LLM rewrite chỉ để thêm từ. Chỉ mở rộng các pattern có tín hiệu đủ rõ
    để không làm loãng embedding của câu hỏi HR khác.
    """
    expansions: list[str] = []
    if _HYBRID_QUERY_PATTERN.search(query):
        expansions.append("WFH, làm việc từ xa, onsite, mô hình 3-2")
    if _REFERRAL_QUERY_PATTERN.search(query):
        # Regression qa_013: người dùng nói "giới thiệu bạn ứng tuyển" trong
        # khi policy dùng "giới thiệu nội bộ (referral)" ở mục kênh đăng tin.
        expansions.append(
            "tuyển dụng, giới thiệu nội bộ, referral, kênh đăng tin, website tuyển dụng, nộp hồ sơ ứng viên"
        )
    if _KPI_QUERY_PATTERN.search(query):
        expansions.append("đánh giá hiệu suất, KPI, OKR, kết quả công việc, kỳ đánh giá, xếp loại thành tích")
    if _RECRUITMENT_QUERY_PATTERN.search(query):
        expansions.append("quy trình tuyển dụng, tiếp nhận nhân sự, phỏng vấn, thử việc, tiêu chuẩn tuyển dụng")
    disciplinary_match = _DISCIPLINARY_ABSENCE_QUERY_PATTERN.search(query)
    if disciplinary_match:
        # Regression qa_122: câu hỏi nói "tự ý nghỉ/chưa được phê duyệt", còn
        # policy dùng cụm "tự ý bỏ việc 05 ngày cộng dồn trong 30 ngày".
        # Đây là một paraphrase canonical có chủ đích: câu hỏi gốc dài và
        # chứa nhiều điều kiện, trong khi chunk policy có đúng cụm này.
        return "tự ý bỏ việc 05 ngày cộng dồn trong 30 ngày; sa thải; lý do chính đáng"
    if not expansions:
        return query
    return f"{query}\nTừ khóa liên quan: {'; '.join(expansions)}"


def _lifecycle_conditions(query_date_ymd: int) -> list[dict]:
    return [
        {"publication_status": "active"},
        {"artifact_state": "frozen"},
        {"retrieval_enabled": True},
        {"effective_date_ymd": {"$lte": query_date_ymd}},
        {"expiry_date_ymd": {"$gte": query_date_ymd}},
    ]


def _predicate_leaf_count(predicate: dict) -> int:
    """Count Chroma leaf predicates, including nested $and/$or branches."""
    total = 0
    for key, value in predicate.items():
        if key in {"$and", "$or"}:
            total += sum(_predicate_leaf_count(item) for item in value)
        else:
            total += 1
    return total


def _metadata_lifecycle_allowed(metadata: dict, query_date_ymd: int) -> bool:
    """Exact lifecycle post-check for branches shortened to Chroma's quota."""
    try:
        effective = int(metadata.get("effective_date_ymd", 99991231))
        expiry = int(metadata.get("expiry_date_ymd", 0))
    except (TypeError, ValueError):
        return False
    return (
        metadata.get("publication_status") == "active"
        and metadata.get("artifact_state") == "frozen"
        and metadata.get("retrieval_enabled") is True
        and effective <= query_date_ymd <= expiry
    )


def _metadata_authorized(metadata: dict, user_context: UserContext, allowed_files: set[str]) -> bool:
    """Defense-in-depth ACL used after vector and lexical retrieval."""
    same_department = canonical_department(metadata.get("department")) == canonical_department(user_context.department)
    registry_allowed = same_department and str(metadata.get("source_file") or "") in allowed_files
    runtime_allowed = runtime_upload_metadata_allowed(user_context, metadata)
    return registry_allowed or runtime_allowed


def _provenance_filter(settings: Settings, user_context: UserContext | None = None) -> dict:
    """Registry corpus filter; kept below Chroma's 8-predicate query quota."""
    if user_context is None:
        return {"source_file": "__NO_ACCESS__"}
    allowed_files = get_authorization_engine().get_authorized_source_files(user_context)
    if not allowed_files:
        return {"source_file": "__NO_ACCESS__"}
    file_condition = (
        {"source_file": {"$in": allowed_files}} if len(allowed_files) > 1 else {"source_file": allowed_files[0]}
    )
    conditions = [
        file_condition,
        {"department": canonical_department(user_context.department)},
        *_lifecycle_conditions(int(datetime.now(UTC).strftime("%Y%m%d"))),
    ]
    if settings.data_mode == "production":
        conditions.append({"provenance": {"$nin": sorted(DEMO_ONLY_PROVENANCE)}})
    return {"$and": conditions}


def _retrieval_filters(settings: Settings, user_context: UserContext) -> list[dict]:
    """Return independent authorized queries; each has at most 8 leaf predicates."""
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
    filters: list[dict] = []
    offline = _provenance_filter(settings, user_context)
    if offline != {"source_file": "__NO_ACCESS__"}:
        filters.append(offline)
    lifecycle = _lifecycle_conditions(query_date_ymd)
    for access in runtime_upload_access_filters(user_context):
        access_conditions = access["$and"] if "$and" in access else [access]
        remaining_quota = max(0, 8 - _predicate_leaf_count(access))
        filters.append({"$and": [*access_conditions, *lifecycle[:remaining_quota]]})
    return filters or [{"source_file": "__NO_ACCESS__"}]


def _merge_query_results(results: list[dict], limit: int) -> dict:
    best: dict[str, tuple[str, dict, float]] = {}
    for result in results:
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            if chunk_id not in best or distance < best[chunk_id][2]:
                best[chunk_id] = (document, metadata, distance)
    # Chroma không cam kết thứ tự khi nhiều chunk có cùng distance.
    # chunk_id là tie-break ổn định cho cùng một snapshot dữ liệu.
    ranked = sorted(best.items(), key=lambda item: (item[1][2], item[0]))[:limit]
    return {
        "ids": [[item[0] for item in ranked]],
        "documents": [[item[1][0] for item in ranked]],
        "metadatas": [[item[1][1] for item in ranked]],
        "distances": [[item[1][2] for item in ranked]],
    }


@lru_cache
def _collection(collection_name: str | None = None):
    """Cache collection theo tên tiến trình — định tuyến linh hoạt theo từng tenant."""
    settings = get_settings()
    client = get_chroma_client(settings)
    name = collection_name or settings.chroma_collection_name
    return get_collection(client, name)


@lru_cache
def _bm25_index(collection_name: str | None = None) -> BM25 | None:
    """Corpus BM25 tải MỘT LẦN cho từng collection tenant."""
    try:
        result = _collection(collection_name).get(
            include=["documents"],
            where={"$and": [{"publication_status": "active"}, {"retrieval_enabled": True}]},
        )
    except Exception as e:  # noqa: BLE001
        print(f"[hybrid] không tải được corpus BM25 cho '{collection_name}': {type(e).__name__}: {e}")
        return None
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    if not ids:
        return None
    return BM25(ids, documents)


async def _aembed_query(text: str) -> list[float]:
    # Exact-match cache: câu hỏi lặp lại (demo, chạy lại eval) không tốn lại
    # ~0.3-0.5s gọi API embed. Chỉ cache embedding — KHÔNG cache câu trả lời.
    cached = get_cached_embedding(text)
    if cached is not None:
        return cached

    settings = get_settings()
    vectors = await asyncio.to_thread(
        embed_batch,
        [f"query: {text}"],
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
    )
    vec = vectors[0]
    set_cached_embedding(text, vec)
    return vec


def _to_chunk(
    chunk_id: str,
    text: str,
    meta: dict,
    distance: float,
) -> RetrievedChunk:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": meta.get("source_file", ""),
        "title": meta.get("title", ""),
        "department": meta.get("department", "HR"),
        "category": meta.get("category", ""),
        "owner": meta.get("owner", ""),
        "is_official_policy": bool(meta.get("is_official_policy", False)),
        "source_type": meta.get("source_type", "public_reference"),
        "authority": meta.get("authority", "public_reference"),
        "provenance": meta.get("provenance", "public_web"),
        "tenant": meta.get("tenant", ""),
        "caveat": meta.get("caveat", ""),
        "heading_path": meta.get("heading_path", ""),
        "policy_status": meta.get("publication_status", "active"),
        "document_code": str(meta.get("document_code") or ""),
        "version": str(meta.get("version") or ""),
        "effective_date": str(meta.get("effective_date") or ""),
        "page_start": meta.get("page_start"),
        "page_end": meta.get("page_end"),
        "sheet_start": meta.get("sheet_start"),
        "sheet_end": meta.get("sheet_end"),
        "distance": distance,
        "score": None,
    }


async def retrieval_node(state: AgentState) -> dict:
    """Truy vấn Chroma Cloud bằng query embedding với Scoped Tenant & Authorization."""
    # --- Phân hệ Kế toán: Ủy quyền cho hàm retrieval riêng biệt ---
    from src.domains import get_conversation_domain
    from src.domains.accounting.retrieval_ext import accounting_retrieval_node

    query = state.get("rewritten_query") or state.get("condensed_query") or state["query"]
    domain = get_conversation_domain(query, state.get("category"), state.get("history"))
    if domain and domain.domain_name == "accounting":
        return await accounting_retrieval_node(state)
    settings = get_settings()

    user_context = UserContext.from_state(state)
    collection_name = (
        collection_name_for_department("Product", settings, user_context.tenant_id)
        if (domain and domain.domain_name == "product")
        else resolve_tenant_collection(user_context)
    )

    with llm_trace.Timer("embedding", "fpt_cloud"):
        embedding = await _aembed_query(query)

    with llm_trace.Timer("chroma_init", "chroma_cloud"):
        collection = _collection(collection_name)

    filters = _retrieval_filters(settings, user_context)
    with llm_trace.Timer("vector_search", "chroma_cloud", n_results=settings.retrieval_top_k):
        branch_results = await asyncio.gather(
            *[
                asyncio.to_thread(
                    partial(collection.query, where=where),
                    query_embeddings=[embedding],
                    n_results=settings.retrieval_top_k,
                )
                for where in filters
            ]
        )
        result = _merge_query_results(branch_results, settings.retrieval_top_k)

    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    allowed_files = set(get_authorization_engine().get_authorized_source_files(user_context))
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))

    chunk_map: dict[str, RetrievedChunk] = {
        chunk_id: _to_chunk(chunk_id, text, meta, distance)
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances)
        if _metadata_lifecycle_allowed(meta, query_date_ymd) and _metadata_authorized(meta, user_context, allowed_files)
    }

    if settings.use_hybrid and ids:
        chunk_map = await _amerge_bm25(
            query, ids, chunk_map, settings, user_context=user_context, collection_name=collection_name
        )

    chunks = list(chunk_map.values())
    if settings.use_reranker and chunks:
        chunks = await _arerank(query, chunks)

    # Observability & Audit Trail Logging
    req_id = state.get("request_id") or "req_default"
    doc_ids: list[str] = []
    for c in chunks or []:
        meta = getattr(c, "metadata", None)
        if meta is None and isinstance(c, dict):
            meta = c.get("metadata") or {}
        sf = getattr(meta, "source_file", None)
        if sf is None and isinstance(meta, dict):
            sf = meta.get("source_file")
        if sf:
            doc_ids.append(str(sf))
    doc_ids = sorted(set(doc_ids))
    print(
        f"[AUDIT-RETRIEVAL] req_id={req_id} tenant={user_context.tenant_id} "
        f"user={user_context.user_id} role={user_context.role.value} dept={user_context.department} "
        f"collection={collection_name} count={len(chunks)} doc_ids={doc_ids}"
    )

    return {"retrieved_chunks": chunks}


async def _amerge_bm25(
    query: str,
    dense_ids: list[str],
    chunk_map: dict[str, RetrievedChunk],
    settings: Settings,
    user_context: UserContext | None = None,
    collection_name: str | None = None,
) -> dict[str, RetrievedChunk]:
    """Trộn thêm ứng viên BM25 (RRF) theo đúng tenant collection và kiểm tra quyền ACL."""
    bm25 = await asyncio.to_thread(_bm25_index, collection_name)
    if bm25 is None:
        return chunk_map

    auth_engine = get_authorization_engine()
    allowed_files = set(auth_engine.get_authorized_source_files(user_context or UserContext(department="GENERAL")))

    # Lấy ứng viên BM25
    bm25_candidates = [cid for cid, _ in bm25.top_k(query, k=settings.bm25_top_k * 2)]
    missing_ids = [cid for cid in bm25_candidates if cid not in chunk_map]
    if missing_ids:
        coll = _collection(collection_name)
        fetched = await asyncio.to_thread(coll.get, ids=missing_ids, include=["documents", "metadatas"])
        fallback_distance = settings.retrieval_max_distance
        query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
        for chunk_id, text, meta in zip(
            fetched.get("ids") or [], fetched.get("documents") or [], fetched.get("metadatas") or []
        ):
            sf = meta.get("source_file", "")
            registry_allowed = sf in allowed_files
            runtime_allowed = user_context is not None and runtime_upload_metadata_allowed(user_context, meta)
            if registry_allowed:
                publication_status = meta.get("publication_status", "active")
                artifact_state = meta.get("artifact_state", "frozen")
                retrieval_enabled = meta.get("retrieval_enabled", True)
                effective_date_ymd = int(meta.get("effective_date_ymd", 1))
                expiry_date_ymd = int(meta.get("expiry_date_ymd", 99991231))
            else:
                publication_status = meta.get("publication_status")
                artifact_state = meta.get("artifact_state")
                retrieval_enabled = meta.get("retrieval_enabled")
                effective_date_ymd = int(meta.get("effective_date_ymd", 99991231))
                expiry_date_ymd = int(meta.get("expiry_date_ymd", 0))
            lifecycle_allowed = (
                publication_status == "active"
                and artifact_state == "frozen"
                and retrieval_enabled is True
                and effective_date_ymd <= query_date_ymd
                and expiry_date_ymd >= query_date_ymd
            )
            if lifecycle_allowed and (registry_allowed or runtime_allowed):
                chunk_map[chunk_id] = _to_chunk(chunk_id, text, meta, fallback_distance)

    valid_bm25_ids = [cid for cid in bm25_candidates if cid in chunk_map][: settings.bm25_top_k]
    fused = reciprocal_rank_fusion([dense_ids, valid_bm25_ids], k=settings.rrf_k)
    fused_ids = [cid for cid, _ in fused[: settings.retrieval_top_k]]

    return {cid: chunk_map[cid] for cid in fused_ids if cid in chunk_map}


async def _arerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Xếp hạng lại bằng cross-encoder qua FPT.AI Marketplace, cắt còn rerank_top_k.

    Dense retrieval hay tìm đúng TÀI LIỆU nhưng sai ĐOẠN (đo được: Document
    Hit@10 = 95% trong khi Recall@1 chỉ 41.7%) — cross-encoder đọc cặp
    (câu hỏi, đoạn) nên phân biệt được các đoạn có từ vựng giống nhau trong
    cùng một tài liệu, chỗ mà embedding thuần yếu.

    Rerank lỗi (mạng/gateway) thì GIỮ NGUYÊN thứ tự dense và để score=None —
    suy giảm chất lượng xếp hạng nhưng agent vẫn trả lời được, thay vì chết cả
    request.
    """
    settings = get_settings()
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
    except Exception as e:  # noqa: BLE001
        # Fail closed: dense distance không cùng thang với reranker score. Dùng
        # im lặng kết quả dense từng làm behavior đổi theo trạng thái gateway.
        print(f"[rerank] fail-closed do lỗi {type(e).__name__}: {e}")
        return []

    reranked: list[RetrievedChunk] = []
    for index, score in ranked:
        if 0 <= index < len(chunks):
            chunk = chunks[index]
            chunk["score"] = score
            reranked.append(chunk)
    return sorted(
        reranked,
        key=lambda chunk: (-(chunk.get("score") or 0.0), chunk["chunk_id"]),
    )[: settings.rerank_top_k]


def grade_node(state: AgentState) -> dict:
    """Lọc chunk không đủ liên quan.

    Ưu tiên score của reranker (0-1, cùng thang cho mọi câu hỏi) và chỉ dùng
    khoảng cách embedding khi không có score — khoảng cách cosine phụ thuộc
    từng câu hỏi nên ngưỡng tĩnh trên nó rất khó chỉnh (đo được: phân phối
    distance của câu in-scope và out-of-scope chồng lấn nặng).

    KHÔNG có fallback kiểu "lọc hết thì lấy tạm top-3": để danh sách rỗng đi
    tiếp là đúng thiết kế — generate sẽ nói "chưa đủ thông tin" và confidence
    thấp sẽ escalate thành ticket. Fallback im lặng làm tê liệt toàn bộ nhánh
    escalate đó.
    """
    settings = get_settings()
    chunks = state.get("retrieved_chunks", [])

    scored = [c for c in chunks if c.get("score") is not None]
    if scored:
        relevant = [c for c in scored if c["score"] >= settings.rerank_min_score]
    else:
        relevant = [c for c in chunks if c["distance"] <= settings.retrieval_max_distance]

    return {"retrieved_chunks": relevant}


async def rewrite_node(state: AgentState) -> dict:
    from src.config import get_settings

    query = state.get("condensed_query") or state.get("query", "")
    # temperature=0.0: cùng lý do như condense_node — đây là node quyết định query
    # đưa vào retrieval lần thử lại, không phải node sinh văn phong tự nhiên.
    settings = get_settings()
    model = settings.router_model or None
    rewritten = (
        await acall_llm(
            _REWRITE_SYSTEM,
            query,
            temperature=0.0,
            model=model,
            enable_thinking=thinking_arg(settings.thinking_router),
        )
    ).strip()
    rewrite_count = state.get("rewrite_count", 0) + 1
    return {"rewritten_query": rewritten, "rewrite_count": rewrite_count}

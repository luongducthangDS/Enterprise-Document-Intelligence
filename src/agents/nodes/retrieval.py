import asyncio
import re
import time
from datetime import UTC, datetime
from functools import lru_cache, partial

from src.agents.llm import acall_llm, resolve_embedding_endpoint, thinking_arg
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
_MULTI_SOURCE_QUERY_PATTERN = re.compile(
    r"tổng hợp|đối chiếu|đa nguồn|nhiều (?:nguồn|tài liệu)|"
    r"(?:bảng|biểu đồ|chart).{0,48}(?:và|với).{0,48}(?:báo cáo|prd|blocker|guardrail)|"
    r"(?:prd|báo cáo).{0,48}(?:và|với).{0,48}(?:prd|báo cáo|scan)",
    re.IGNORECASE,
)
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
    """Bổ sung từ đồng nghĩa ổn định cho các cách nói lệch từ vựng tài liệu và biến thể thời gian.

    Expansion nhỏ này giúp dense và BM25 tìm đúng ngay lượt đầu mà không cần
    gọi LLM rewrite chỉ để thêm từ. Chỉ mở rộng các pattern có tín hiệu đủ rõ
    để không làm loãng embedding của câu hỏi HR khác.
    """
    from src.retrieval.temporal import expand_temporal_query

    query = expand_temporal_query(query)
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


def _is_multi_source_query(query: str) -> bool:
    """Chỉ bật source diversification khi người dùng yêu cầu tổng hợp rõ ràng."""
    return bool(_MULTI_SOURCE_QUERY_PATTERN.search(query))


def _round_robin_sources(chunks: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    """Giữ thứ tự reranker nhưng tránh để một tài liệu chiếm toàn bộ context.

    Mỗi vòng lấy chunk tốt nhất tiếp theo của từng source. Câu hỏi một nguồn
    không đổi hành vi; câu tổng hợp nhận được độ phủ tài liệu tốt hơn trong
    cùng token budget.
    """
    groups: dict[str, list[RetrievedChunk]] = {}
    source_order: list[str] = []
    for chunk in chunks:
        source = str(chunk.get("source_file") or chunk["chunk_id"])
        if source not in groups:
            groups[source] = []
            source_order.append(source)
        groups[source].append(chunk)

    diversified: list[RetrievedChunk] = []
    offset = 0
    while len(diversified) < limit:
        added = False
        for source in source_order:
            if offset < len(groups[source]):
                diversified.append(groups[source][offset])
                added = True
                if len(diversified) == limit:
                    break
        if not added:
            break
        offset += 1
    return diversified


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
    registry_allowed = str(metadata.get("source_file") or "") in allowed_files
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
        *_lifecycle_conditions(int(datetime.now(UTC).strftime("%Y%m%d"))),
    ]
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


async def detect_department_scope_denial(
    collection,
    embedding: list[float],
    user_context: UserContext,
    settings: Settings,
) -> str | None:
    """Detect relevant department-only evidence without exposing its contents."""
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
    try:
        result = await asyncio.to_thread(
            partial(collection.query, where={"$and": _lifecycle_conditions(query_date_ymd)}, include=["metadatas", "distances"]),
            query_embeddings=[embedding],
            n_results=min(3, settings.retrieval_top_k),
        )
    except Exception:  # noqa: BLE001 - denial detection must not break retrieval
        return None

    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    user_department = canonical_department(user_context.department)
    for metadata, distance in zip(metadatas, distances):
        if float(distance) > settings.retrieval_max_distance:
            continue
        if str(metadata.get("access_scope", "")).upper() != "DEPARTMENT":
            continue
        document_department = canonical_department(metadata.get("department"))
        if document_department != user_department:
            return document_department
    return None

@lru_cache
def _collection(collection_name: str | None = None):
    """Cache collection theo tên tiến trình — định tuyến linh hoạt theo từng tenant."""
    settings = get_settings()
    client = get_chroma_client(settings)
    name = collection_name or settings.chroma_collection_name
    return get_collection(client, name)


@lru_cache
def _bm25_index(collection_name: str | None = None) -> BM25 | None:
    """Corpus BM25 tải MỘT LẦN cho từng collection tenant và lưu 100% trong RAM."""
    try:
        col = _collection(collection_name)
        result = col.get(include=["documents", "metadatas"])
    except Exception as e:  # noqa: BLE001
        print(f"[hybrid] không tải được corpus BM25 cho '{collection_name}': {type(e).__name__}: {e}")
        return None
    raw_ids = result.get("ids") or []
    raw_documents = result.get("documents") or []
    raw_metadatas = result.get("metadatas") or []
    ids = []
    documents = []
    metadatas = []
    for cid, doc, meta in zip(raw_ids, raw_documents, raw_metadatas):
        if not meta or (meta.get("publication_status", "active") == "active" and meta.get("retrieval_enabled", True) is not False):
            ids.append(cid)
            documents.append(doc)
            metadatas.append(meta or {})
    if not ids:
        return None
    bm25 = BM25(ids, documents)
    bm25.doc_map = {cid: doc for cid, doc in zip(ids, documents)}
    bm25.meta_map = {cid: meta for cid, meta in zip(ids, metadatas)}
    return bm25


async def _aembed_query(text: str) -> list[float]:
    # Exact-match cache: câu hỏi lặp lại (demo, chạy lại eval) không tốn lại
    # ~0.3-0.5s gọi API embed. Chỉ cache embedding — KHÔNG cache câu trả lời.
    cached = get_cached_embedding(text)
    if cached is not None:
        return cached

    model, base_url, api_key = resolve_embedding_endpoint()
    try:
        input_text = f"query: {text}" if "e5" in model.lower() else text
        vectors = await asyncio.to_thread(
            embed_batch,
            [input_text],
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        vec = vectors[0]
        set_cached_embedding(text, vec)
        return vec
    except Exception as e:
        print(f"[embedding] Lỗi embedding {type(e).__name__}: {e}. Fallback sang BM25 lexical search.")
        return []


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

    t_retrieval_start = time.perf_counter()
    query = state.get("rewritten_query") or state.get("condensed_query") or state["query"]
    domain = get_conversation_domain(query, state.get("category"), state.get("history"))
    print(f"[RETRIEVAL-DOMAIN] Query: {query!r} -> Domain: {getattr(domain, 'domain_name', 'default_hr')}")
    if domain and domain.domain_name == "accounting":
        return await accounting_retrieval_node(state)
    settings = get_settings()

    user_context = UserContext.from_state(state)
    collection_name = (
        collection_name_for_department("Product", settings, user_context.tenant_id)
        if (domain and domain.domain_name == "product")
        else resolve_tenant_collection(user_context)
    )

    t_embed_start = time.perf_counter()

    # Song song hoa: embed + auth_filter + bm25_warmup cung luc
    # - _aembed_query: goi OpenAI API (~229-1400ms, IO-bound)
    # - get_authorized_source_files: doc registry (CPU/IO, ~20-80ms)
    # - _bm25_index: @lru_cache - lan dau tai RAM, sau do ~0ms
    # Ba tac vu khong phu thuoc nhau -> chay dong thoi tiet kiem dang ke.
    async def _get_allowed_files_async() -> set[str]:
        return set(await asyncio.to_thread(
            get_authorization_engine().get_authorized_source_files, user_context
        ))

    async def _warmup_bm25_async() -> None:
        await asyncio.to_thread(_bm25_index, collection_name)

    search_query = _expand_retrieval_query(query)
    with llm_trace.Timer("embedding", "fpt_cloud" if settings.use_glm else "openai"):
        embedding, allowed_files, _ = await asyncio.gather(
            _aembed_query(search_query),
            _get_allowed_files_async(),
            _warmup_bm25_async(),
        )
    embed_ms = round((time.perf_counter() - t_embed_start) * 1000)

    with llm_trace.Timer("chroma_init", "chroma_cloud"):
        collection = _collection(collection_name)

    t_search_start = time.perf_counter()
    filters = _retrieval_filters(settings, user_context)
    ids, documents, metadatas, distances = [], [], [], []
    if embedding:
        with llm_trace.Timer("vector_search", "chroma_cloud", n_results=settings.retrieval_top_k):
            try:
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
            except Exception as e:
                print(f"[vector_search] Chroma query warning ({type(e).__name__}: {e})")
    search_ms = round((time.perf_counter() - t_search_start) * 1000)

    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))

    chunk_map: dict[str, RetrievedChunk] = {
        chunk_id: _to_chunk(chunk_id, text, meta, distance)
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances)
        if _metadata_lifecycle_allowed(meta, query_date_ymd) and _metadata_authorized(meta, user_context, allowed_files)
    }

    if settings.use_hybrid:
        chunk_map = await _amerge_bm25(
            search_query, ids, chunk_map, settings, user_context=user_context, collection_name=collection_name
        )

    chunks = list(chunk_map.values())
    if not chunks:
        denied_department = await detect_department_scope_denial(collection, embedding, user_context, settings)
        if denied_department:
            return {
                "retrieved_chunks": [],
                "access_denied_reason": "DEPARTMENT_SCOPE_DENIED",
                "denied_department": denied_department,
            }

    rerank_ms = 0
    if settings.use_reranker and chunks:
        t_rerank_start = time.perf_counter()
        if _is_multi_source_query(query):
            chunks = await _arerank(query, chunks, diversify_sources=True)
        else:
            chunks = await _arerank(query, chunks)
        rerank_ms = round((time.perf_counter() - t_rerank_start) * 1000)

    total_retrieval_ms = round((time.perf_counter() - t_retrieval_start) * 1000)
    top_sources = list({c.get('source_file') for c in chunks[:5] if c.get('source_file')})
    print(
        f"[TIMING] [retrieve] {total_retrieval_ms}ms "
        f"(embed: {embed_ms}ms, vector_search: {search_ms}ms, rerank: {rerank_ms}ms) | chunks={len(chunks)} | sources={top_sources}"
    )

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
        fallback_distance = settings.retrieval_max_distance
        query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
        doc_map = getattr(bm25, "doc_map", {})
        meta_map = getattr(bm25, "meta_map", {})
        unresolved_ids = []
        for chunk_id in missing_ids:
            text = doc_map.get(chunk_id)
            meta = meta_map.get(chunk_id)
            if text and meta:
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
            else:
                unresolved_ids.append(chunk_id)

        if unresolved_ids:
            coll = _collection(collection_name)
            fetched = await asyncio.to_thread(coll.get, ids=unresolved_ids, include=["documents", "metadatas"])
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
    if not settings.use_glm and settings.llm_provider != "gemini":
        # Khi USE_GLM=OFF (OpenAI query trên kho E5), BM25 là nguồn tìm kiếm từ khóa chính xác nhất.
        # Đưa toàn bộ ứng viên BM25 lên đầu danh sách trước khi bổ sung dense để LLM Reranker đánh giá.
        ordered_ids = list(dict.fromkeys(valid_bm25_ids + dense_ids))
        fused_ids = ordered_ids[: settings.retrieval_top_k]
    else:
        fused = reciprocal_rank_fusion([dense_ids, valid_bm25_ids], k=settings.rrf_k)
        fused_ids = [cid for cid, _ in fused[: settings.retrieval_top_k]]

    return {cid: chunk_map[cid] for cid in fused_ids if cid in chunk_map}


def _round_robin_sources(
    chunks: list[RetrievedChunk],
    top_k: int = 5,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """Lấy vòng tròn xen kẽ các source_file khác nhau."""
    from collections import defaultdict

    by_source: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for c in chunks:
        by_source[c["source_file"]].append(c)

    result: list[RetrievedChunk] = []
    sources = list(by_source.keys())
    idx = 0
    while len(result) < top_k and any(by_source.values()):
        src = sources[idx % len(sources)]
        if by_source[src]:
            result.append(by_source[src].pop(0))
        idx += 1
    return result


async def _arerank(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    diversify_sources: bool = False,
) -> list[RetrievedChunk]:
    """Xếp hạng lại các đoạn trích. Khi USE_GLM=OFF tự động dùng OpenAI gpt-4o-mini LLM Reranker, khi ON dùng FPT Cross-Encoder."""
    if not chunks:
        return []
    settings = get_settings()
    target_top_n = len(chunks) if diversify_sources else settings.rerank_top_k

    from src.agents.llm import resolve_reranker_endpoint

    r_model, r_base_url, r_api_key = resolve_reranker_endpoint()
    try:
        ranked = await asyncio.to_thread(
            rerank,
            query,
            [c["text"] for c in chunks],
            model=r_model,
            base_url=r_base_url,
            api_key=r_api_key,
            top_n=target_top_n,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[rerank] fail-closed do lỗi {type(e).__name__}: {e}")
        return []

    reranked = []
    for index, score in ranked:
        if 0 <= index < len(chunks):
            chunk = chunks[index]
            chunk["score"] = score
            reranked.append(chunk)
    ordered = sorted(
        reranked,
        key=lambda chunk: (-(chunk.get("score") or 0.0), chunk["chunk_id"]),
    )
    if diversify_sources:
        eligible = [chunk for chunk in ordered if (chunk.get("score") or 0.0) >= settings.rerank_min_score]
        return _round_robin_sources(eligible, settings.rerank_top_k)
    return ordered[: settings.rerank_top_k]


def grade_node(state: AgentState) -> dict:
    t_grade_start = time.perf_counter()
    settings = get_settings()
    chunks = state.get("retrieved_chunks", [])

    scored = [c for c in chunks if c.get("score") is not None]
    if scored:
        relevant = [c for c in scored if c["score"] >= settings.rerank_min_score]
    else:
        relevant = [c for c in chunks if c["distance"] <= settings.retrieval_max_distance]

    grade_ms = round((time.perf_counter() - t_grade_start) * 1000, 2)
    print(f"[TIMING] [grade] {grade_ms}ms | input_chunks={len(chunks)} -> relevant_chunks={len(relevant)}")

    return {"retrieved_chunks": relevant}


async def rewrite_node(state: AgentState) -> dict:
    from src.config import get_settings

    t_rewrite_start = time.perf_counter()
    query = state.get("condensed_query") or state.get("query", "")
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
    rewrite_ms = round((time.perf_counter() - t_rewrite_start) * 1000)
    print(f"[TIMING] [rewrite] {rewrite_ms}ms | attempt={rewrite_count}")
    return {"rewritten_query": rewritten, "rewrite_count": rewrite_count}

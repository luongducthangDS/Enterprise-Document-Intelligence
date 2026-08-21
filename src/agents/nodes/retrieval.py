import asyncio
import json
import re
from datetime import datetime, timezone

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc

from functools import lru_cache, partial

from src.agents.llm import acall_llm, thinking_arg
from src.agents.state import AgentState, RetrievedChunk
from src.config import Settings, get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.ingestion.metadata import DEMO_ONLY_PROVENANCE, load_registry
from src.observability import llm_trace
from src.retrieval.bm25 import BM25
from src.retrieval.cache import get_cached_embedding, set_cached_embedding
from src.retrieval.hybrid import fuse_candidate_ids, reciprocal_rank_fusion

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
            "tuyển dụng, giới thiệu nội bộ, referral, kênh đăng tin, "
            "website tuyển dụng, nộp hồ sơ ứng viên"
        )
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


from src.security import UserContext, get_authorization_engine


def _provenance_filter(settings: Settings, user_context: UserContext | None = None) -> dict | None:
    """Chặn dữ liệu ở TẦNG TRUY VẤN (Enterprise Authorization Engine / Access Control Filter)."""
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
    user = user_context or UserContext(department="GENERAL")
    auth_engine = get_authorization_engine()
    allowed_files = auth_engine.get_authorized_source_files(user)
    if not allowed_files:
        return {"source_file": "__NO_ACCESS__"}

    file_condition = (
        {"source_file": {"$in": allowed_files}}
        if len(allowed_files) > 1
        else {"source_file": allowed_files[0]}
    )
    conditions: list[dict] = [
        file_condition,
        {"publication_status": "active"},
        {"artifact_state": "frozen"},
        {"retrieval_enabled": True},
        {"effective_date_ymd": {"$lte": query_date_ymd}},
        {"expiry_date_ymd": {"$gte": query_date_ymd}},
    ]

    if settings.data_mode == "production":
        conditions.append({"provenance": {"$nin": sorted(DEMO_ONLY_PROVENANCE)}})
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


from src.security.tenant_resolver import resolve_tenant_collection
from src.security.authorization import get_authorization_engine
from src.security.models import UserContext


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
        "is_official_policy": bool(meta.get("is_official_policy", False)),
        "source_type": meta.get("source_type", "public_reference"),
        "authority": meta.get("authority", "public_reference"),
        "provenance": meta.get("provenance", "public_web"),
        "tenant": meta.get("tenant", ""),
        "caveat": meta.get("caveat", ""),
        "heading_path": meta.get("heading_path", ""),
        "policy_status": meta.get("publication_status", "active"),
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
    from src.domains.accounting.retrieval_ext import accounting_retrieval_node, is_accounting_request

    if is_accounting_request(state):
        return await accounting_retrieval_node(state)

    query = state.get("rewritten_query") or state.get("condensed_query") or state["query"]
    settings = get_settings()

    user_context = UserContext.from_state(state)
    collection_name = resolve_tenant_collection(user_context)

    with llm_trace.Timer("embedding", "fpt_cloud"):
        embedding = await _aembed_query(query)

    with llm_trace.Timer("chroma_init", "chroma_cloud"):
        collection = _collection(collection_name)

    where = _provenance_filter(settings, user_context=user_context)
    with llm_trace.Timer("vector_search", "chroma_cloud", n_results=settings.retrieval_top_k):
        result = await asyncio.to_thread(
            partial(collection.query, where=where) if where else collection.query,
            query_embeddings=[embedding],
            n_results=settings.retrieval_top_k,
        )

    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    chunk_map: dict[str, RetrievedChunk] = {
        chunk_id: _to_chunk(chunk_id, text, meta, distance)
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances)
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
    print(
        f"[AUDIT-RETRIEVAL] req_id={req_id} tenant={user_context.tenant_id} "
        f"user={user_context.user_id} role={user_context.role.value} dept={user_context.department} "
        f"collection={collection_name} count={len(chunks)}"
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
        fetched = await asyncio.to_thread(
            coll.get, ids=missing_ids, include=["documents", "metadatas"]
        )
        fallback_distance = settings.retrieval_max_distance
        for chunk_id, text, meta in zip(
            fetched.get("ids") or [], fetched.get("documents") or [], fetched.get("metadatas") or []
        ):
            if meta.get("source_file") in allowed_files:
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
    except Exception as e:  # noqa: BLE001 — không để lỗi rerank làm chết cả câu hỏi
        print(f"[rerank] bỏ qua do lỗi {type(e).__name__}: {e}")
        return chunks[: settings.rerank_top_k]

    reranked: list[RetrievedChunk] = []
    for index, score in ranked:
        if 0 <= index < len(chunks):
            chunk = chunks[index]
            chunk["score"] = score
            reranked.append(chunk)
    return reranked[: settings.rerank_top_k]


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

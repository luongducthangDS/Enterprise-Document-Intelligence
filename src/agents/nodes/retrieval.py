import asyncio
from functools import lru_cache

from src.agents.llm import acall_llm
from src.agents.state import AgentState, RetrievedChunk
from src.config import Settings, get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.retrieval.bm25 import BM25
from src.retrieval.hybrid import fuse_candidate_ids
from src.services.fpt_client import embed_batch, rerank

_REWRITE_SYSTEM = """Bạn giúp viết lại câu hỏi HR để tìm kiếm tài liệu chính sách chính xác hơn. Giữ nguyên ý định gốc của người hỏi, nhưng diễn đạt lại rõ ràng hơn, thêm từ khoá chuyên môn/luật liên quan nếu có thể. Chỉ trả về câu hỏi đã viết lại, không giải thích."""


@lru_cache
def _collection():
    """Cache collection theo tiến trình — tránh tạo lại CloudClient (bắt tay xác
    thực) ở mỗi request."""
    settings = get_settings()
    client = get_chroma_client(settings)
    return get_collection(client, settings.chroma_collection_name)


@lru_cache
def _bm25_index() -> BM25 | None:
    """Corpus BM25 tải MỘT LẦN từ Chroma Cloud (không phải data/chunks/*.json —
    file đó gitignored, không tồn tại trên server), cache theo tiến trình như
    _collection(). Trả None nếu tải lỗi/collection rỗng để hybrid tự tắt an
    toàn (xem fuse_candidate_ids) thay vì làm chết cả request retrieval."""
    try:
        result = _collection().get(include=["documents"])
    except Exception as e:  # noqa: BLE001 — lỗi tải corpus phụ không được chặn retrieval chính
        print(f"[hybrid] không tải được corpus BM25: {type(e).__name__}: {e}")
        return None
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    if not ids:
        return None
    return BM25(ids, documents)


async def _aembed_query(text: str) -> list[float]:
    settings = get_settings()
    vectors = await asyncio.to_thread(
        embed_batch,
        [f"query: {text}"],
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
    )
    return vectors[0]


def _to_chunk(chunk_id: str, text: str, meta: dict, distance: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        source_file=meta.get("source_file", ""),
        title=meta.get("title", ""),
        category=meta.get("category", ""),
        is_official_policy=bool(meta.get("is_official_policy", False)),
        source_type=str(meta.get("source_type") or ""),
        page_start=meta.get("page_start"),
        page_end=meta.get("page_end"),
        distance=distance,
        score=None,
    )


async def retrieval_node(state: AgentState) -> dict:
    settings = get_settings()
    query = state.get("rewritten_query") or state.get("query", "")
    embedding = await _aembed_query(query)

    collection = _collection()
    result = await asyncio.to_thread(
        collection.query, query_embeddings=[embedding], n_results=settings.retrieval_top_k
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
        chunk_map = await _amerge_bm25(query, ids, chunk_map, settings)

    chunks = list(chunk_map.values())
    if settings.use_reranker and chunks:
        chunks = await _arerank(query, chunks)

    return {"retrieved_chunks": chunks}


async def _amerge_bm25(
    query: str, dense_ids: list[str], chunk_map: dict[str, RetrievedChunk], settings: Settings
) -> dict[str, RetrievedChunk]:
    """Trộn thêm ứng viên BM25 (RRF) rồi trả về đúng tập chunk theo thứ tự
    trộn — ứng viên chỉ đến từ BM25 (không nằm trong dense_ids) cần lấy riêng
    text/metadata qua collection.get() vì query dense không hề thấy chúng."""
    bm25 = await asyncio.to_thread(_bm25_index)
    fused_ids = fuse_candidate_ids(
        dense_ids=dense_ids,
        bm25=bm25,
        query=query,
        bm25_top_k=settings.bm25_top_k,
        rrf_k=settings.rrf_k,
        fused_top_k=settings.retrieval_top_k,
    )

    missing_ids = [cid for cid in fused_ids if cid not in chunk_map]
    if missing_ids:
        fetched = await asyncio.to_thread(
            _collection().get, ids=missing_ids, include=["documents", "metadatas"]
        )
        # Chunk chỉ đến từ BM25 không có cosine distance thật — không có gì để
        # ước lượng nó tốt hơn "biên ngoài cùng còn được coi là liên quan"
        # (retrieval_max_distance). Vô hại trong pipeline hiện tại vì distance
        # chỉ dùng khi reranker tắt/lỗi (fallback ở grade_node/confidence_node);
        # có use_reranker=True nên score thật của reranker mới quyết định.
        fallback_distance = settings.retrieval_max_distance
        for chunk_id, text, meta in zip(
            fetched.get("ids") or [], fetched.get("documents") or [], fetched.get("metadatas") or []
        ):
            chunk_map[chunk_id] = _to_chunk(chunk_id, text, meta, fallback_distance)

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
    query = state.get("query", "")
    rewritten = (await acall_llm(_REWRITE_SYSTEM, query, temperature=0.3)).strip()
    rewrite_count = state.get("rewrite_count", 0) + 1
    return {"rewritten_query": rewritten, "rewrite_count": rewrite_count}

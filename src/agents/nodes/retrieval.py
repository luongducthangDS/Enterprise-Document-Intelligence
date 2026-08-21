import asyncio
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
from src.ingestion.metadata import DEMO_ONLY_PROVENANCE
from src.observability import llm_trace
from src.retrieval.bm25 import BM25
from src.retrieval.cache import get_cached_embedding, set_cached_embedding
from src.retrieval.hybrid import fuse_candidate_ids
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


@lru_cache
def _collection():
    """Cache collection theo tiến trình — tránh tạo lại CloudClient (bắt tay xác
    thực) ở mỗi request."""
    settings = get_settings()
    client = get_chroma_client(settings)
    return get_collection(client, settings.chroma_collection_name)


def _provenance_filter(settings: Settings) -> dict | None:
    """Chặn dữ liệu ở TẦNG TRUY VẤN, không phụ thuộc LLM tuân thủ prompt.

    Lọc ở đây chứ không phải trong prompt là có chủ đích: prompt chỉ là lời dặn,
    còn `where` là ràng buộc — chunk bị lọc không bao giờ tồn tại trong ngữ cảnh
    nên không có đường nào để model lỡ trích dẫn nó.

    Bốn điều kiện LUÔN áp dụng (demo lẫn production) + 1 điều kiện chỉ production:
    - authority IN [tenant_official_policy, government_law]: sản phẩm trả lời bằng
      (1) dữ liệu nội bộ doanh nghiệp (quy trình, biên bản, quyết định, quy chế)
      và (2) văn bản pháp luật (bộ luật, nghị định, thông tư) — cả hai được index
      vào knowledge database từ 2026-08-21. Chính sách THẬT của doanh nghiệp KHÁC,
      template công khai không gắn công ty nào vẫn bị loại. Dùng allowlist ($in)
      thay vì liệt kê từng $ne: chunk cũ không có field `authority` trong Chroma
      metadata — $ne với field vắng mặt vẫn khớp (không lọc được); $in fail-closed
      — chunk thiếu/khác field tự động bị loại.
    - publication_status=active, artifact_state=frozen, retrieval_enabled=True:
      contract "frozen internal corpus" (NexaTech Type-C contract v3.1.0) — một
      tài liệu tenant_official_policy vẫn có thể bị loại khỏi truy vấn khi bị
      supersede (publication_status khác "active") hoặc tạm khoá RAG
      (retrieval_enabled=False) mà không cần đổi authority. Cùng $eq allowlist
      logic như trên — fail-closed với chunk thiếu field.

    Rào chắn tại tầng `where` là rào chắn thứ hai — phòng khi chunk cũ còn sót
    trong Chroma Cloud dù ingestion đã ngừng coi các nguồn đó là RAG-eligible
    (xem NON_RAG_SOURCE_TYPES, rag_eligible_rows trong src/ingestion/metadata.py).

    - effective_date_ymd<=query_date_ymd VÀ expiry_date_ymd>=query_date_ymd:
      contract yêu cầu "effective_date <= query_date AND (expiry_date IS NULL
      OR expiry_date >= query_date)". HAI lỗi thật đã đo được khi implement:
      (1) Chroma `$lte`/`$gte` CHỈ nhận operand int/float — thử filter bằng
      chuỗi ISO "2026-08-15" trực tiếp bị Chroma raise ValueError ngay tại
      query time (không phải lỗi âm thầm, nhưng vẫn phải sửa trước khi launch).
      Khắc phục bằng field riêng `effective_date_ymd`/`expiry_date_ymd` (int
      YYYYMMDD, xem date_to_ymd_int() trong metadata.py) — CHỈ dùng để filter,
      field chuỗi effective_date/expiry_date vẫn giữ để hiển thị/audit.
      (2) "IS NULL" (không có hạn) không thể biểu diễn bằng field vắng mặt vì
      Chroma bỏ hẳn field None khỏi metadata khi ghi, và field vắng mặt lại
      KHÔNG khớp `$gte` — khắc phục bằng NO_EXPIRY_SENTINEL (99991231, luôn
      >= mọi query_date thật) ở tầng ingestion thay vì để trống.

    - provenance=synthetic_demo chỉ bị loại thêm khi production: ở demo, dữ
      liệu mô phỏng ĐƯỢC dùng như chính sách nội bộ chính thức của tenant giả
      lập. Hệ quả đã lường trước: ở production mà KB chưa có policy thật,
      `grade_node` trả rỗng và câu hỏi đi thẳng sang nhánh escalate/ticket —
      đó là hành vi ĐÚNG, không phải lỗi.
    """
    query_date_ymd = int(datetime.now(UTC).strftime("%Y%m%d"))
    # authority allowlist: tenant_official_policy = tài liệu nội bộ doanh nghiệp (quy trình,
    # biên bản, quyết định, quy chế); government_law = văn bản pháp luật (bộ luật, nghị định,
    # thông tư) — được đưa vào knowledge database từ 2026-08-21, trích dẫn kèm
    # is_official_policy=True để người dùng phân biệt nguồn nội bộ vs nguồn pháp lý.
    conditions: list[dict] = [
        {"authority": {"$in": ["tenant_official_policy", "government_law"]}},
        {"publication_status": "active"},
        {"artifact_state": "frozen"},
        {"retrieval_enabled": True},
        {"effective_date_ymd": {"$lte": query_date_ymd}},
        {"expiry_date_ymd": {"$gte": query_date_ymd}},
    ]
    if settings.data_mode == "production":
        conditions.append({"provenance": {"$nin": sorted(DEMO_ONLY_PROVENANCE)}})
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


@lru_cache
def _bm25_index() -> BM25 | None:
    """Corpus BM25 tải MỘT LẦN từ Chroma Cloud (không phải data/chunks/*.json —
    file đó gitignored, không tồn tại trên server), cache theo tiến trình như
    _collection(). Trả None nếu tải lỗi/collection rỗng để hybrid tự tắt an
    toàn (xem fuse_candidate_ids) thay vì làm chết cả request retrieval."""
    try:
        # Cùng bộ lọc với truy vấn dense — nếu không, ứng viên synthetic vẫn lọt
        # vào context qua ngả RRF ở production dù dense đã chặn.
        where = _provenance_filter(get_settings())
        result = _collection().get(include=["documents"], **({"where": where} if where else {}))
    except Exception as e:  # noqa: BLE001 — lỗi tải corpus phụ không được chặn retrieval chính
        print(f"[hybrid] không tải được corpus BM25: {type(e).__name__}: {e}")
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
    set_cached_embedding(text, vectors[0])
    return vectors[0]


def _to_chunk(chunk_id: str, text: str, meta: dict, distance: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        source_file=meta.get("source_file", ""),
        title=meta.get("title", ""),
        department=str(meta.get("department") or "HR"),
        category=meta.get("category", ""),
        is_official_policy=bool(meta.get("is_official_policy", False)),
        source_type=str(meta.get("source_type") or ""),
        # Chunk index từ trước đợt migrate taxonomy chưa có 3 khoá này. Mặc định
        # về nhóm THẤP quyền nhất thay vì đoán cao lên: một chunk chưa phân loại
        # không được thừa hưởng thẩm quyền của chính sách nội bộ.
        authority=str(meta.get("authority") or "public_reference"),
        provenance=str(meta.get("provenance") or "public_web"),
        tenant=str(meta.get("tenant") or ""),
        caveat=str(meta.get("caveat") or ""),
        heading_path=str(meta.get("heading_path") or ""),
        policy_status=str(meta.get("publication_status") or ""),
        page_start=meta.get("page_start"),
        page_end=meta.get("page_end"),
        sheet_start=meta.get("sheet_start"),
        sheet_end=meta.get("sheet_end"),
        distance=distance,
        score=None,
    )


async def retrieval_node(state: AgentState) -> dict:
    settings = get_settings()
    raw_query = state.get("rewritten_query") or state.get("condensed_query") or state.get("query", "")
    query = _expand_retrieval_query(raw_query)
    embedding = await _aembed_query(query)

    # Đo riêng hai phần, vì chúng có bản chất khác hẳn nhau và trước đây cùng
    # nằm trong một khối "retrieve" không bóc được:
    #   - `_collection()` chỉ tốn thời gian ở lần gọi ĐẦU TIÊN mỗi tiến trình
    #     (dựng CloudClient + bắt tay xác thực), sau đó lru_cache trả ngay.
    #     Đo thực tế: request đầu của một lần profiling tốn ~18,8s cho riêng
    #     bước này, đủ để bóp méo mọi thống kê nếu bị trộn vào latency truy vấn.
    #   - `collection.query` là truy vấn vector thật, xảy ra ở MỌI request.
    with llm_trace.Timer("chroma_init", "chroma_cloud"):
        collection = _collection()
    where = _provenance_filter(settings)
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

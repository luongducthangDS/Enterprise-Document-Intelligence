import asyncio
from functools import lru_cache

from src.agents.llm import acall_llm
from src.agents.state import AgentState, RetrievedChunk
from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.services.fpt_client import embed_batch

_REWRITE_SYSTEM = """Bạn giúp viết lại câu hỏi HR để tìm kiếm tài liệu chính sách chính xác hơn. Giữ nguyên ý định gốc của người hỏi, nhưng diễn đạt lại rõ ràng hơn, thêm từ khoá chuyên môn/luật liên quan nếu có thể. Chỉ trả về câu hỏi đã viết lại, không giải thích."""


@lru_cache
def _collection():
    """Cache collection theo tiến trình — tránh tạo lại CloudClient (bắt tay xác
    thực) ở mỗi request."""
    settings = get_settings()
    client = get_chroma_client(settings)
    return get_collection(client, settings.chroma_collection_name)


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

    chunks: list[RetrievedChunk] = [
        RetrievedChunk(
            chunk_id=chunk_id,
            text=text,
            source_file=meta.get("source_file", ""),
            title=meta.get("title", ""),
            category=meta.get("category", ""),
            is_official_policy=bool(meta.get("is_official_policy", False)),
            page_start=meta.get("page_start"),
            page_end=meta.get("page_end"),
            distance=distance,
        )
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances)
    ]
    return {"retrieved_chunks": chunks}


def grade_node(state: AgentState) -> dict:
    """Lọc chunk theo ngưỡng khoảng cách (heuristic đơn giản — LLM-based grading
    để dành làm bước nâng cao sau nếu còn thời gian)."""
    settings = get_settings()
    chunks = state.get("retrieved_chunks", [])
    relevant = [c for c in chunks if c["distance"] <= settings.retrieval_max_distance]
    return {"retrieved_chunks": relevant}


async def rewrite_node(state: AgentState) -> dict:
    query = state.get("query", "")
    rewritten = (await acall_llm(_REWRITE_SYSTEM, query, temperature=0.3)).strip()
    rewrite_count = state.get("rewrite_count", 0) + 1
    return {"rewritten_query": rewritten, "rewrite_count": rewrite_count}

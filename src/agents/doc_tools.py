"""Tool làm việc trên CẢ tài liệu (search_policies chỉ trả top chunk):
get_document, compare_documents, extract_structured.

ACL giống hệt retrieval: registry quyết định file nào người dùng được xem
(`get_authorized_source_files`), cộng kiểm vòng đời (`_metadata_lifecycle_allowed`)
và runtime upload (`_metadata_authorized`) trên từng chunk. File không có quyền
và file không tồn tại trả CÙNG một thông báo, để tool không thành cách dò xem
tài liệu nào tồn tại.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime

from src.agents.llm import acall_llm
from src.agents.nodes.retrieval import _collection, _metadata_authorized, _metadata_lifecycle_allowed, _to_chunk
from src.agents.state import AgentState, RetrievedChunk
from src.config import get_settings
from src.ingestion.indexer import collection_name_for_department
from src.security import UserContext, get_authorization_engine

NOT_AVAILABLE = "Không tìm thấy tài liệu này, hoặc người dùng không có quyền xem."
_MAX_DOC_CHARS = 12_000


def _collections_for(user_context: UserContext) -> list[str | None]:
    s = get_settings()
    return [
        None,  # collection tenant (HR + tài liệu chung)
        collection_name_for_department("Product", s, user_context.tenant_id),
        collection_name_for_department("Accounting", s, user_context.tenant_id),
    ]


async def get_document(state: AgentState, source_file: str) -> list[RetrievedChunk] | None:
    """Mọi chunk của một tài liệu theo thứ tự, hoặc None nếu không có/không có quyền."""
    user_context = UserContext.from_state(state)
    allowed = set(await asyncio.to_thread(get_authorization_engine().get_authorized_source_files, user_context))
    today = int(datetime.now(UTC).strftime("%Y%m%d"))

    def _load() -> list[RetrievedChunk]:
        for name in dict.fromkeys(_collections_for(user_context)):
            got = _collection(name).get(where={"source_file": source_file}, include=["documents", "metadatas"])
            rows = [
                (i, d, m)
                for i, d, m in zip(got["ids"], got["documents"], got["metadatas"])
                if _metadata_lifecycle_allowed(m, today) and _metadata_authorized(m, user_context, allowed)
            ]
            if rows:
                rows.sort(key=lambda r: int(r[2].get("chunk_index") or 0))
                return [{**_to_chunk(i, d, m, 0.0), "score": 0.5} for i, d, m in rows]
        return []

    chunks = await asyncio.to_thread(_load)
    return chunks or None


def doc_text(chunks: list[RetrievedChunk], limit: int = _MAX_DOC_CHARS) -> str:
    text = "\n\n".join(f"[{c.get('heading_path') or ''}]\n{c.get('text', '')}" for c in chunks)
    return text[:limit]


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.lower()) if len(t) > 1}


def top_sections(chunks: list[RetrievedChunk], aspect: str, k: int = 3) -> list[RetrievedChunk]:
    # ponytail: xếp theo số từ trùng với khía cạnh cần so; tài liệu nội bộ ngắn (vài chục chunk)
    # nên đủ. Khi tài liệu dài hoặc khía cạnh diễn đạt khác từ ngữ thì đổi sang embedding.
    want = _tokens(aspect)
    ranked = sorted(chunks, key=lambda c: -len(want & _tokens(f"{c.get('heading_path', '')} {c.get('text', '')}")))
    return ranked[:k]


_EXTRACT_SYSTEM = (
    "Bạn trích xuất thông tin từ MỘT tài liệu nội bộ. Chỉ dùng nội dung tài liệu được cung cấp. "
    "Trả về JSON object: mỗi khóa là tên trường được yêu cầu, giá trị là "
    '{"value": <chuỗi ngắn hoặc null>, "quote": <câu trích NGUYÊN VĂN từ tài liệu làm căn cứ, hoặc null>}. '
    "Không có thông tin thì value=null, quote=null. Không giải thích, chỉ JSON."
)


def norm_ws(text: str) -> str:
    return " ".join(text.lower().split())


def verify_extraction(raw: dict, fields: list[str], source: str) -> dict:
    """Giữ một giá trị chỉ khi `quote` thật sự có trong tài liệu (chống bịa số liệu)."""
    src = norm_ws(source)
    out = {}
    for f in fields:
        item = raw.get(f) if isinstance(raw.get(f), dict) else {}
        value, quote = item.get("value"), item.get("quote")
        grounded = bool(value) and bool(quote) and norm_ws(str(quote)) in src
        out[f] = {"value": value if grounded else None, "quote": quote if grounded else None, "grounded": grounded}
    return out


async def extract_structured(chunks: list[RetrievedChunk], fields: list[str]) -> dict:
    text = doc_text(chunks)
    reply = await acall_llm(
        _EXTRACT_SYSTEM,
        f"Trường cần trích: {json.dumps(fields, ensure_ascii=False)}\n\n<TÀI_LIỆU>\n{text}\n</TÀI_LIỆU>",
        timeout=40,
        retries=1,
    )
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        raw = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        raw = {}
    return verify_extraction(raw, fields, text)

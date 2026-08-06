"""Cache exact-match cho embedding của câu hỏi — thuần stdlib, in-memory.

Phạm vi CHỦ ĐÍCH hẹp: chỉ cache embedding theo đúng chuỗi câu hỏi (sau khi
chuẩn hoá whitespace + lowercase), KHÔNG cache câu trả lời và KHÔNG có
semantic cache. Semantic cache (trả câu trả lời cũ khi embedding "đủ giống")
đã được cân nhắc và bác bỏ: hai câu HR khác nghĩa hoàn toàn vẫn có thể có
cosine similarity > 0.95 ("nghỉ phép năm" vs "nghỉ không lương") — trả nhầm
câu trả lời về quyền lợi là lỗi nghiêm trọng hơn nhiều so với chậm vài giây
(xem CLAUDE.md [2026-08-06] Phase 3).
"""

import hashlib
import time
from collections import OrderedDict
from typing import Any


class LRUCacheWithTTL:
    """LRU cache có TTL — entry quá hạn bị coi như miss và dọn khi chạm tới."""

    def __init__(self, maxsize: int = 512, ttl_seconds: float = 7200) -> None:
        self._entries: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, stored_at = entry
        if time.monotonic() - stored_at >= self._ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._entries:
            del self._entries[key]
        self._entries[key] = (value, time.monotonic())
        if len(self._entries) > self._maxsize:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)


def _query_key(query: str) -> str:
    normalized = " ".join(query.split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# Cache theo tiến trình, giống pattern lru_cache của _collection()/_bm25_index().
# ~1000 float/vector × 512 entry ≈ vài MB — không đáng kể.
_embedding_cache = LRUCacheWithTTL(maxsize=512, ttl_seconds=7200)


def get_cached_embedding(query: str) -> list[float] | None:
    return _embedding_cache.get(_query_key(query))


def set_cached_embedding(query: str, embedding: list[float]) -> None:
    _embedding_cache.set(_query_key(query), embedding)

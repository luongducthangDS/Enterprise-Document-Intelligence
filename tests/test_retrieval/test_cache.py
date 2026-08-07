from src.retrieval import cache
from src.retrieval.cache import LRUCacheWithTTL, get_cached_embedding, set_cached_embedding


class TestLRUCacheWithTTL:
    def test_get_returns_none_on_miss(self):
        c = LRUCacheWithTTL(maxsize=2, ttl_seconds=100)
        assert c.get("missing") is None

    def test_set_then_get(self):
        c = LRUCacheWithTTL(maxsize=2, ttl_seconds=100)
        c.set("k", [1.0, 2.0])
        assert c.get("k") == [1.0, 2.0]

    def test_evicts_least_recently_used_when_full(self):
        c = LRUCacheWithTTL(maxsize=2, ttl_seconds=100)
        c.set("a", 1)
        c.set("b", 2)
        c.get("a")  # "a" vừa được dùng -> "b" là LRU
        c.set("c", 3)
        assert c.get("b") is None
        assert c.get("a") == 1
        assert c.get("c") == 3

    def test_expired_entry_is_a_miss(self, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(cache.time, "monotonic", lambda: clock["now"])
        c = LRUCacheWithTTL(maxsize=2, ttl_seconds=60)
        c.set("k", 42)
        clock["now"] += 61
        assert c.get("k") is None
        assert len(c) == 0

    def test_overwrite_refreshes_ttl(self, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(cache.time, "monotonic", lambda: clock["now"])
        c = LRUCacheWithTTL(maxsize=2, ttl_seconds=60)
        c.set("k", 1)
        clock["now"] += 50
        c.set("k", 2)
        clock["now"] += 50  # 100s từ set đầu nhưng chỉ 50s từ set sau
        assert c.get("k") == 2


class TestEmbeddingCacheHelpers:
    def test_roundtrip(self):
        set_cached_embedding("Tôi được nghỉ mấy ngày phép?", [0.1, 0.2])
        assert get_cached_embedding("Tôi được nghỉ mấy ngày phép?") == [0.1, 0.2]

    def test_key_normalizes_whitespace_and_case(self):
        """Cùng câu hỏi gõ thừa khoảng trắng/khác hoa thường phải hit chung 1
        entry — không tạo 2 lần gọi API embed cho cùng nội dung."""
        set_cached_embedding("Nghỉ  thai sản   bao lâu?", [0.5])
        assert get_cached_embedding("nghỉ thai sản bao lâu?") == [0.5]

    def test_different_queries_do_not_collide(self):
        set_cached_embedding("câu hỏi A", [1.0])
        set_cached_embedding("câu hỏi B", [2.0])
        assert get_cached_embedding("câu hỏi A") == [1.0]
        assert get_cached_embedding("câu hỏi B") == [2.0]

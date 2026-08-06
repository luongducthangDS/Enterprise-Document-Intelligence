from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nodes.retrieval import _arerank, grade_node, retrieval_node, rewrite_node
from src.config import get_settings
from src.retrieval.bm25 import BM25


def _chunk(chunk_id: str, distance: float = 0.1, score=None, text: str = "nội dung") -> dict:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": "doc.md",
        "title": "Chính sách A",
        "category": "leave_policies",
        "is_official_policy": True,
        "page_start": None,
        "page_end": None,
        "distance": distance,
        "score": score,
    }


class TestRetrievalNode:
    @pytest.mark.asyncio
    async def test_parses_chroma_query_result_into_chunks(self):
        chroma_result = {
            "ids": [["doc::0001", "doc::0002"]],
            "documents": [["Nội dung 1", "Nội dung 2"]],
            "metadatas": [
                [
                    {
                        "source_file": "doc.md",
                        "title": "Chính sách A",
                        "category": "leave_policies",
                        "is_official_policy": True,
                        "page_start": 1,
                        "page_end": 1,
                    },
                    {
                        "source_file": "doc2.md",
                        "title": "Chính sách B",
                        "category": "leave_policies",
                        "is_official_policy": False,
                    },
                ]
            ],
            "distances": [[0.12, 0.44]],
        }
        mock_collection = MagicMock()
        mock_collection.query.return_value = chroma_result

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1, 0.2, 0.3])),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
            # Không gọi reranker thật: unit test không được phụ thuộc mạng.
            patch("src.agents.nodes.retrieval._arerank", new=AsyncMock(side_effect=lambda q, c: c)),
        ):
            result = await retrieval_node({"query": "Tôi được nghỉ mấy ngày?"})

        chunks = result["retrieved_chunks"]
        assert len(chunks) == 2
        assert chunks[0]["chunk_id"] == "doc::0001"
        assert chunks[0]["distance"] == 0.12
        assert chunks[1]["is_official_policy"] is False
        # chunk thứ 2 không có page_start/page_end trong metadata -> None, không KeyError
        assert chunks[1]["page_start"] is None

    @pytest.mark.asyncio
    async def test_uses_rewritten_query_over_original_when_present(self):
        mock_collection = MagicMock()
        mock_collection.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        mock_embed = AsyncMock(return_value=[0.1])

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=mock_embed),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
        ):
            await retrieval_node({"query": "gốc", "rewritten_query": "đã viết lại"})

        mock_embed.assert_awaited_once_with("đã viết lại")


class TestRetrievalNodeHybrid:
    """use_hybrid=False theo mặc định (xem TestRetrievalNode ở trên, không đổi
    hành vi). Các test này bật cờ tường minh và tắt lại sau khi xong — lru_cache
    (settings, _collection, _bm25_index) là module-level nên phải patch
    get_settings thay vì set field trực tiếp để không rò rỉ sang test khác."""

    def _hybrid_settings(self):
        settings = get_settings().model_copy(update={"use_hybrid": True, "use_reranker": False})
        return settings

    @pytest.mark.asyncio
    async def test_bm25_only_candidate_is_fetched_and_included(self):
        chroma_result = {
            "ids": [["a"]],
            "documents": [["nội dung a"]],
            "metadatas": [[{"source_file": "a.md", "title": "A", "category": "x", "is_official_policy": True}]],
            "distances": [[0.1]],
        }
        mock_collection = MagicMock()
        mock_collection.query.return_value = chroma_result
        # "b" chỉ đến từ BM25, không nằm trong kết quả dense query ở trên -> phải
        # được lấy riêng qua collection.get(ids=["b"], ...).
        mock_collection.get.return_value = {
            "ids": ["b"],
            "documents": ["nội dung b"],
            "metadatas": [{"source_file": "b.md", "title": "B", "category": "x", "is_official_policy": False}],
        }
        bm25 = BM25(["a", "b"], ["nội dung a về nghỉ phép", "nội dung b về nghỉ phép đặc biệt"])

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1])),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
            patch("src.agents.nodes.retrieval._bm25_index", return_value=bm25),
            patch("src.agents.nodes.retrieval.get_settings", return_value=self._hybrid_settings()),
        ):
            result = await retrieval_node({"query": "nghỉ phép đặc biệt"})

        ids = {c["chunk_id"] for c in result["retrieved_chunks"]}
        assert "b" in ids
        b_chunk = next(c for c in result["retrieved_chunks"] if c["chunk_id"] == "b")
        assert b_chunk["text"] == "nội dung b"
        assert b_chunk["source_file"] == "b.md"

    @pytest.mark.asyncio
    async def test_bm25_load_failure_falls_back_to_dense_only(self):
        """_bm25_index() trả None khi tải corpus lỗi — hybrid phải tự tắt, không
        được làm chết cả request retrieval."""
        chroma_result = {
            "ids": [["a"]],
            "documents": [["nội dung a"]],
            "metadatas": [[{"source_file": "a.md", "title": "A", "category": "x", "is_official_policy": True}]],
            "distances": [[0.1]],
        }
        mock_collection = MagicMock()
        mock_collection.query.return_value = chroma_result

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1])),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
            patch("src.agents.nodes.retrieval._bm25_index", return_value=None),
            patch("src.agents.nodes.retrieval.get_settings", return_value=self._hybrid_settings()),
        ):
            result = await retrieval_node({"query": "câu hỏi"})

        assert [c["chunk_id"] for c in result["retrieved_chunks"]] == ["a"]


class TestRerank:
    @pytest.mark.asyncio
    async def test_reorders_by_relevance_score_and_attaches_it(self):
        chunks = [_chunk("a", distance=0.10), _chunk("b", distance=0.20), _chunk("c", distance=0.30)]
        # Gateway trả về thứ tự đã xếp lại: chunk "c" liên quan nhất.
        with patch("src.agents.nodes.retrieval.rerank", return_value=[(2, 0.91), (0, 0.40), (1, 0.02)]):
            result = await _arerank("câu hỏi", chunks)

        assert [c["chunk_id"] for c in result] == ["c", "a", "b"]
        assert result[0]["score"] == 0.91

    @pytest.mark.asyncio
    async def test_keeps_dense_order_when_gateway_fails(self):
        """Lỗi rerank chỉ được làm giảm chất lượng xếp hạng, không được làm chết
        cả câu hỏi (regression: bản cũ để lỗi tải model lọt ra ngoài node)."""
        chunks = [_chunk("a"), _chunk("b")]
        with patch("src.agents.nodes.retrieval.rerank", side_effect=RuntimeError("gateway 503")):
            result = await _arerank("câu hỏi", chunks)

        assert [c["chunk_id"] for c in result] == ["a", "b"]
        assert all(c["score"] is None for c in result)


class TestGradeNode:
    def test_filters_by_rerank_score_when_available(self):
        state = {"retrieved_chunks": [_chunk("a", score=0.8), _chunk("b", score=0.001)]}
        result = grade_node(state)
        assert [c["chunk_id"] for c in result["retrieved_chunks"]] == ["a"]

    def test_falls_back_to_distance_when_score_is_none(self):
        """Regression: bản cũ so `c.get("score", -99) > 0.0` trong khi
        RetrievedChunk luôn có key `score` = None → TypeError khi reranker vắng
        mặt, làm chết toàn bộ agent trên máy không cài được reranker."""
        state = {"retrieved_chunks": [_chunk("a", distance=0.1), _chunk("b", distance=0.9)]}
        result = grade_node(state)
        assert [c["chunk_id"] for c in result["retrieved_chunks"]] == ["a"]

    def test_returns_empty_instead_of_falling_back_to_top_k(self):
        """Không có chunk nào đủ liên quan thì phải để rỗng — generate sẽ báo
        thiếu thông tin và confidence thấp sẽ escalate. Fallback im lặng kiểu
        "lấy tạm top-3" làm tê liệt nhánh escalate."""
        state = {"retrieved_chunks": [_chunk("a", score=0.001), _chunk("b", score=0.0)]}
        assert grade_node(state)["retrieved_chunks"] == []

    def test_empty_chunks_stays_empty(self):
        result = grade_node({"retrieved_chunks": []})
        assert result["retrieved_chunks"] == []


class TestRewriteNode:
    @pytest.mark.asyncio
    async def test_increments_rewrite_count_and_sets_rewritten_query(self):
        with patch("src.agents.nodes.retrieval.acall_llm", new=AsyncMock(return_value="  câu hỏi rõ hơn  ")):
            result = await rewrite_node({"query": "câu gốc", "rewrite_count": 1})
        assert result["rewritten_query"] == "câu hỏi rõ hơn"
        assert result["rewrite_count"] == 2

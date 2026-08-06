from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nodes.retrieval import grade_node, retrieval_node, rewrite_node


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


class TestGradeNode:
    def test_filters_out_chunks_beyond_distance_threshold(self):
        state = {
            "retrieved_chunks": [
                {"distance": 0.1},
                {"distance": 0.9},  # settings.retrieval_max_distance mặc định 0.65
            ]
        }
        result = grade_node(state)
        assert len(result["retrieved_chunks"]) == 1
        assert result["retrieved_chunks"][0]["distance"] == 0.1

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

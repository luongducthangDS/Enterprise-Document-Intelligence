from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nodes.generation import finalize_node, generate_node, hallucination_check_node


class TestGenerateNode:
    @pytest.mark.asyncio
    async def test_builds_citations_from_retrieved_chunks(self):
        chunks = [
            {
                "chunk_id": "doc::0001",
                "text": "Nội dung",
                "source_file": "doc.md",
                "title": "Chính sách nghỉ phép",
                "category": "leave_policies",
                "is_official_policy": True,
                "page_start": 3,
                "page_end": 3,
                "distance": 0.1,
            }
        ]
        with patch(
            "src.agents.nodes.generation.acall_llm",
            new=AsyncMock(return_value="  Bạn được nghỉ 12 ngày [Nguồn 1].  "),
        ):
            result = await generate_node({"query": "Tôi được nghỉ mấy ngày?", "retrieved_chunks": chunks})

        assert result["generated_answer"] == "Bạn được nghỉ 12 ngày [Nguồn 1]."
        assert len(result["citations"]) == 1
        assert result["citations"][0]["source_file"] == "doc.md"
        assert result["citations"][0]["page_start"] == 3

    @pytest.mark.asyncio
    async def test_no_chunks_still_returns_answer_and_empty_citations(self):
        with patch("src.agents.nodes.generation.acall_llm", new=AsyncMock(return_value="Chưa đủ thông tin.")):
            result = await generate_node({"query": "abc", "retrieved_chunks": []})
        assert result["citations"] == []


class TestHallucinationCheckNode:
    @pytest.mark.asyncio
    async def test_pass_verdict_does_not_increment_retry_count(self):
        with patch("src.agents.nodes.generation.acall_llm", new=AsyncMock(return_value="PASS")):
            result = await hallucination_check_node(
                {"retrieved_chunks": [], "generated_answer": "abc", "hallucination_retry_count": 0}
            )
        assert result["hallucination_passed"] is True
        assert result["hallucination_retry_count"] == 0

    @pytest.mark.asyncio
    async def test_fail_verdict_increments_retry_count(self):
        with patch("src.agents.nodes.generation.acall_llm", new=AsyncMock(return_value="FAIL — có số liệu bịa")):
            result = await hallucination_check_node(
                {"retrieved_chunks": [], "generated_answer": "abc", "hallucination_retry_count": 1}
            )
        assert result["hallucination_passed"] is False
        assert result["hallucination_retry_count"] == 2


class TestFinalizeNode:
    def test_appends_citation_footer_when_citations_present(self):
        state = {
            "generated_answer": "Bạn được nghỉ 12 ngày.",
            "citations": [
                {
                    "chunk_id": "doc::0001",
                    "source_file": "doc.md",
                    "title": "Chính sách nghỉ phép",
                    "page_start": 3,
                    "page_end": 3,
                    "is_official_policy": False,
                }
            ],
        }
        result = finalize_node(state)
        assert "Nguồn tham khảo" in result["response"]
        assert "trang 3" in result["response"]
        assert "không phải chính sách công ty thật" in result["response"]

    def test_no_citations_returns_answer_unchanged(self):
        result = finalize_node({"generated_answer": "Chưa đủ thông tin.", "citations": []})
        assert result["response"] == "Chưa đủ thông tin."

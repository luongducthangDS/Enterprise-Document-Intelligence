from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.graph import agent


@pytest.mark.asyncio
async def test_greeting_flow_skips_rag_and_returns_direct_response():
    with patch(
        "src.agents.nodes.router.acall_llm", new=AsyncMock(side_effect=["greeting", "Chào bạn, mình có thể giúp gì?"])
    ):
        result = await agent.ainvoke({"query": "Chào bạn"})

    assert result["intent"] == "greeting"
    assert result["response"] == "Chào bạn, mình có thể giúp gì?"
    assert "retrieved_chunks" not in result


@pytest.mark.asyncio
async def test_ambiguous_flow_asks_clarifying_question():
    with patch(
        "src.agents.nodes.router.acall_llm",
        new=AsyncMock(side_effect=["ambiguous", "Bạn muốn hỏi về nghỉ phép năm hay nghỉ ốm?"]),
    ):
        result = await agent.ainvoke({"query": "Tôi muốn nghỉ"})

    assert result["needs_clarification"] is True
    assert result["response"] == "Bạn muốn hỏi về nghỉ phép năm hay nghỉ ốm?"


@pytest.mark.asyncio
async def test_out_of_scope_flow_escalates_without_calling_retrieval():
    # Không mock retrieval/embedding: nếu router lỡ route sai sang nhánh RAG,
    # node sẽ crash vì gọi FPT.AI/Chroma thật -> test tự fail thay vì
    # âm thầm pass, xác nhận đúng nhánh "retrieve" bị bỏ qua hoàn toàn.
    with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="out_of_scope_or_personal")):
        result = await agent.ainvoke({"query": "Lương của tôi tháng này bị trừ bao nhiêu?"})

    assert "retrieved_chunks" not in result
    assert result["escalate"] is True
    assert result["escalate_reason"] == "out_of_scope"
    assert result["ticket_department"] == "CB"


@pytest.mark.asyncio
async def test_hr_question_flow_returns_grounded_answer_with_citations():
    chroma_result = {
        "ids": [["leave::0001"]],
        "documents": [["Nhân viên chính thức được nghỉ 12 ngày phép năm."]],
        "metadatas": [
            [
                {
                    "source_file": "leave.md",
                    "title": "Chính sách nghỉ phép",
                    "category": "leave_policies",
                    "is_official_policy": True,
                    "page_start": 1,
                    "page_end": 1,
                }
            ]
        ],
        "distances": [[0.05]],
    }
    mock_collection = MagicMock()
    mock_collection.query.return_value = chroma_result

    with (
        patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")),
        patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
        patch(
            "src.agents.nodes.generation.acall_llm",
            new=AsyncMock(side_effect=["Bạn được nghỉ 12 ngày phép năm [Nguồn 1].", "PASS"]),
        ),
    ):
        result = await agent.ainvoke({"query": "Tôi được nghỉ bao nhiêu ngày phép năm?"})

    assert result.get("escalate") is not True
    assert "12 ngày" in result["response"]
    assert "Nguồn tham khảo" in result["response"]
    assert result["citations"][0]["source_file"] == "leave.md"


@pytest.mark.asyncio
async def test_hr_question_with_no_relevant_chunks_escalates_after_rewrite_retry():
    empty_chroma_result = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    mock_collection = MagicMock()
    mock_collection.query.return_value = empty_chroma_result

    with (
        patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")),
        patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
        patch("src.agents.nodes.retrieval.acall_llm", new=AsyncMock(return_value="câu hỏi viết lại")),
        patch(
            "src.agents.nodes.generation.acall_llm",
            new=AsyncMock(side_effect=["Chưa đủ thông tin để trả lời.", "PASS"]),
        ),
    ):
        result = await agent.ainvoke({"query": "Câu hỏi không có tài liệu liên quan"})

    # max_rewrite_retries mặc định = 1 -> retrieve -> grade -> rewrite -> retrieve -> grade -> generate
    assert result["rewrite_count"] == 1
    assert result["retrieved_chunks"] == []
    assert result["escalate"] is True
    assert result["escalate_reason"] == "low_confidence"

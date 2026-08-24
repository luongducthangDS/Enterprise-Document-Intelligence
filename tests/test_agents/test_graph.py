from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.graph import agent, route_after_knowledge_lookup
from src.agents.nodes.escalation import department_access_denied_node


def test_knowledge_lookup_is_wired_and_routes_safely():
    assert "knowledge_lookup" in agent.get_graph().nodes
    assert route_after_knowledge_lookup({"skip_retrieval": True}) == "finalize"
    assert route_after_knowledge_lookup({"skip_retrieval": False}) == "retrieve"


def test_department_scope_denial_is_clear_and_does_not_create_ticket():
    result = department_access_denied_node({"denied_department": "FINANCE"})

    assert "phòng ban khác" in result["response"]
    assert "không nằm trong phạm vi truy cập" in result["response"]
    assert result["escalate"] is False
    assert result["escalate_reason"] == "department_scope_denied"
    assert result["citations"] == []


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
    assert result["escalate_reason"] == "personal_data_required"
    assert result["ticket_department"] == "CB"


@pytest.mark.asyncio
async def test_pure_statutory_flow_bypasses_retrieval_and_ticket():
    """NexaTech Type-C contract v3.1.0, routing_precedence priority 2: câu hỏi
    luật thuần tuý phải OUT_OF_SCOPE, KHÔNG retrieval, KHÔNG tạo ticket.
    Không mock retrieval/embedding: nếu router lỡ route sai sang nhánh RAG,
    node sẽ crash vì gọi FPT.AI/Chroma thật -> test tự fail thay vì âm thầm pass."""
    with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="pure_statutory")):
        result = await agent.ainvoke(
            {"query": "Điều 112 Bộ luật Lao động 2019 quy định về chế độ nghỉ lễ, tết như thế nào?"}
        )

    assert "retrieved_chunks" not in result
    assert result["escalate"] is False
    assert result["citations"] == []
    assert result["response"].startswith("[OUT_OF_SCOPE]")
    assert "NexaTech" in result["response"]


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
        patch("src.agents.nodes.retrieval._metadata_authorized", return_value=True),
        patch("src.agents.nodes.retrieval._metadata_lifecycle_allowed", return_value=True),
        patch(
            "src.agents.nodes.generation.acall_llm",
            new=AsyncMock(side_effect=["Bạn được nghỉ 12 ngày phép năm [Nguồn 1].", "PASS"]),
        ),
    ):
        result = await agent.ainvoke(
            {
                "query": "Tôi được nghỉ bao nhiêu ngày phép năm?",
                "tenant_id": "nexatech",
                "user_id": "graph-test-user",
                "department": "HR",
                "user_role": "EMPLOYEE",
            }
        )

    assert result.get("escalate") is not True
    assert "12 ngày" in result["response"]
    assert "Nguồn tham khảo" not in result["response"]
    assert result["citations"][0]["source_file"] == "leave.md"


@pytest.mark.asyncio
async def test_unanswerable_generation_skips_hallucination_check_and_escalates():
    """answerable=False (model phát INSUFFICIENT_MARKER) -> đi thẳng confidence,
    KHÔNG gọi hallucination check (câu "không đủ thông tin" không có claim nào
    để kiểm chứng — tiết kiệm 1 LLM call trên toàn nhánh escalate).

    Mock generation.acall_llm với side_effect CHỈ 1 phần tử: nếu graph vẫn gọi
    hallucination check (lần gọi thứ 2), mock cạn side_effect và test tự fail —
    xác nhận đúng node bị bỏ qua chứ không chỉ tin kết quả cuối."""
    from src.agents.nodes.generation import INSUFFICIENT_MARKER

    chroma_result = {
        "ids": [["x::0001"]],
        "documents": [["Nội dung về chủ đề khác."]],
        "metadatas": [
            [{"source_file": "x.md", "title": "Tài liệu X", "category": "leave_policies", "is_official_policy": True}]
        ],
        "distances": [[0.05]],
    }
    mock_collection = MagicMock()
    mock_collection.query.return_value = chroma_result

    with (
        patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")),
        patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1, 0.2])),
        patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
        patch("src.agents.nodes.retrieval._metadata_authorized", return_value=True),
        patch("src.agents.nodes.retrieval._metadata_lifecycle_allowed", return_value=True),
        patch(
            "src.agents.nodes.generation.acall_llm",
            new=AsyncMock(side_effect=[f"{INSUFFICIENT_MARKER} Đoạn trích không nói về đồng phục."]),
        ),
    ):
        result = await agent.ainvoke(
            {
                "query": "Chính sách đồng phục nhân viên là gì?",
                "tenant_id": "nexatech",
                "user_id": "graph-test-user",
                "department": "HR",
                "user_role": "EMPLOYEE",
            }
        )

    assert result["answerable"] is False
    assert "hallucination_retry_count" not in result  # node check chưa từng chạy
    assert result["escalate"] is True
    assert result["escalate_reason"] == "low_confidence"


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
        result = await agent.ainvoke(
            {
                "query": "Câu hỏi không có tài liệu liên quan",
                "tenant_id": "nexatech",
                "user_id": "graph-test-user",
                "department": "HR",
                "user_role": "EMPLOYEE",
            }
        )

    # max_rewrite_retries mặc định = 1 -> retrieve -> grade -> rewrite -> retrieve -> grade -> generate
    assert result["rewrite_count"] == 1
    assert result["retrieved_chunks"] == []
    assert result["escalate"] is True
    assert result["escalate_reason"] == "low_confidence"

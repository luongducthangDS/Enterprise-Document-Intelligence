from unittest.mock import AsyncMock, patch

import pytest

from src.agents.service import answer, astream_answer, sanitize_citations


def _citation(**overrides) -> dict:
    base = {
        "chunk_id": "doc::0001",
        "source_file": "doc.md",
        "title": "Chính sách nghỉ phép",
        "category": "leave_policies",
        "page_start": 1,
        "page_end": 1,
        "is_official_policy": True,
    }
    base.update(overrides)
    return base


class TestAnswer:
    @pytest.mark.asyncio
    async def test_hr_question_happy_path_has_no_ticket_draft(self):
        state = {
            "response": "Bạn được nghỉ 12 ngày.",
            "intent": "hr_question",
            "confidence_score": 0.95,
            "citations": [_citation()],
        }
        with patch("src.agents.service.agent.ainvoke", new=AsyncMock(return_value=state)):
            result = await answer("Tôi được nghỉ mấy ngày?")

        assert result.response == "Bạn được nghỉ 12 ngày."
        assert result.confidence_score == 0.95
        assert result.citations[0].source_file == "doc.md"
        assert result.escalate is False
        assert result.ticket_draft is None

    def test_sanitizes_pii_from_client_facing_citation_metadata(self):
        citations = sanitize_citations(
            [
                _citation(
                    source_file="owner-hr@company.com.pdf",
                    title="Contact 0912345678",
                )
            ]
        )

        assert "hr@company.com" not in citations[0].source_file
        assert "0912345678" not in citations[0].title

    @pytest.mark.asyncio
    async def test_redacts_pii_from_non_rag_response(self):
        state = {
            "response": "Contact hr@company.com",
            "intent": "greeting",
        }
        with patch("src.agents.service.agent.ainvoke", new=AsyncMock(return_value=state)):
            result = await answer("Hello")

        assert "hr@company.com" not in result.response
        assert state["guardrail_pii_redacted"] is True

    @pytest.mark.asyncio
    async def test_escalated_state_produces_ticket_draft_from_state_fields(self):
        state = {
            "response": "Mình đã tạo yêu cầu hỗ trợ...",
            "intent": "out_of_scope_or_personal",
            "query": "Lương của tôi tháng này bị trừ bao nhiêu?",
            "escalate": True,
            "escalate_reason": "out_of_scope",
            "confidence_score": None,
            "ticket_category": "compensation_policies",
            "ticket_department": "CB",
            "ticket_priority": "Medium",
        }
        with patch("src.agents.service.agent.ainvoke", new=AsyncMock(return_value=state)):
            result = await answer("Lương của tôi tháng này bị trừ bao nhiêu?")

        assert result.escalate is True
        assert result.ticket_draft is not None
        assert result.ticket_draft.employee_question == state["query"]
        assert result.ticket_draft.target_department == "CB"
        assert result.ticket_draft.priority == "Medium"

    @pytest.mark.asyncio
    async def test_competitor_decline_has_no_ticket_draft(self):
        """escalate=False dù escalate_reason='competitor_question' — không có
        gì để HR công ty mình xử lý, không được tạo ticket."""
        state = {
            "response": "Mình chỉ hỗ trợ chính sách công ty mình.",
            "intent": "out_of_scope_or_personal",
            "escalate": False,
            "escalate_reason": "competitor_question",
        }
        with patch("src.agents.service.agent.ainvoke", new=AsyncMock(return_value=state)):
            result = await answer("Viettel có chính sách nghỉ phép thế nào?")

        assert result.escalate is False
        assert result.escalate_reason == "competitor_question"
        assert result.ticket_draft is None

    @pytest.mark.asyncio
    async def test_ambiguous_state_surfaces_clarifying_question(self):
        state = {
            "response": "Bạn muốn hỏi nghỉ phép năm hay nghỉ ốm?",
            "intent": "ambiguous",
            "needs_clarification": True,
            "clarifying_question": "Bạn muốn hỏi nghỉ phép năm hay nghỉ ốm?",
        }
        with patch("src.agents.service.agent.ainvoke", new=AsyncMock(return_value=state)):
            result = await answer("Tôi muốn nghỉ")

        assert result.needs_clarification is True
        assert result.clarifying_question == "Bạn muốn hỏi nghỉ phép năm hay nghỉ ốm?"
        assert result.ticket_draft is None

    @pytest.mark.asyncio
    async def test_missing_optional_state_fields_do_not_raise(self):
        """State tối thiểu (vd nhánh greeting chỉ set response+intent) không
        được làm AgentAnswer validation crash vì thiếu field optional."""
        with patch(
            "src.agents.service.agent.ainvoke",
            new=AsyncMock(return_value={"response": "Chào bạn!", "intent": "greeting"}),
        ):
            result = await answer("Chào bạn")

        assert result.response == "Chào bạn!"
        assert result.citations == []
        assert result.escalate is False


def _fake_astream(steps: list[dict]):
    """Giả lập `agent.astream(state, stream_mode="updates")` — mỗi item trong
    `steps` là 1 dict `{node_name: delta}`, đúng shape LangGraph thật trả về
    (đã verify thủ công bằng smoke test trên graph thật trước khi viết
    astream_answer, xem lịch sử trao đổi 2026-08-10)."""

    async def _gen(state, **kwargs):
        for step in steps:
            for node_name, delta in step.items():
                state.update(delta)
            yield step

    return _gen


class TestAstreamAnswer:
    @pytest.mark.asyncio
    async def test_emits_status_for_known_nodes_only(self):
        steps = [
            {"router": {"intent": "hr_question"}},
            {"grade": {"retrieved_chunks": []}},  # không có status message -> bỏ qua
            {"generate": {"generated_answer": "12 ngày.", "citations": [], "answerable": True}},
            {"confidence": {"confidence_score": 0.9}},  # code thuần -> bỏ qua
            {"finalize": {"response": "12 ngày."}},
        ]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("Mấy ngày phép?")]

        statuses = [e["value"] for e in events if e["type"] == "status"]
        assert statuses == [
            "Đang phân tích yêu cầu...",
            "Đang tìm trong tài liệu HR...",
            "Đang mở rộng phạm vi tìm kiếm...",
            "Đang kiểm tra độ chính xác câu trả lời...",
        ]

    @pytest.mark.asyncio
    async def test_condense_status_skipped_when_no_history(self):
        """condense_node là 0-cost skip khi không có history (xem condense.py)
        — không nên báo status 'đang xử lý' cho việc không thật sự chạy."""
        steps = [
            {"condense": {"condensed_query": "abc"}},
            {"router": {"intent": "hr_question"}},
            {"finalize": {"response": "abc", "citations": []}},
        ]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("abc", history=None)]

        statuses = [e["value"] for e in events if e["type"] == "status"]
        assert statuses == ["Đang phân tích yêu cầu...", "Đang tìm trong tài liệu HR..."]

    @pytest.mark.asyncio
    async def test_condense_status_shown_when_history_present(self):
        steps = [
            {"condense": {"condensed_query": "abc, cụ thể hơn"}},
            {"router": {"intent": "hr_question"}},
            {"finalize": {"response": "abc", "citations": []}},
        ]
        history = [{"role": "user", "content": "câu trước"}, {"role": "assistant", "content": "trả lời trước"}]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("abc", history=history)]

        statuses = [e["value"] for e in events if e["type"] == "status"]
        assert statuses == [
            "Đang xử lý ngữ cảnh hội thoại...",
            "Đang phân tích yêu cầu...",
            "Đang tìm trong tài liệu HR...",
        ]

    @pytest.mark.asyncio
    async def test_emits_tool_events_for_retrieve_node(self):
        steps = [
            {"router": {"intent": "hr_question"}},
            {"retrieve": {"retrieved_chunks": []}},
            {"finalize": {"response": "abc"}},
        ]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("abc")]

        tool_events = [e for e in events if e["type"] in ("tool_start", "tool_end")]
        assert tool_events == [
            {"type": "tool_start", "tool": "hr_policy_search"},
            {"type": "tool_end", "tool": "hr_policy_search"},
        ]

    @pytest.mark.asyncio
    async def test_answer_delta_chunks_reassemble_to_original_response(self):
        long_answer = " ".join(f"từ{i}" for i in range(40))
        steps = [{"finalize": {"response": long_answer, "citations": []}}]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("abc")]

        deltas = [e["content"] for e in events if e["type"] == "answer_delta"]
        assert len(deltas) > 1  # thật sự bị chia nhỏ, không phải 1 cục
        assert "".join(deltas) == long_answer

    @pytest.mark.asyncio
    async def test_emits_citation_events_from_state(self):
        citation = {
            "chunk_id": "doc::0001",
            "source_file": "doc.md",
            "title": "Chính sách nghỉ phép",
            "category": "leave_policies",
            "page_start": 3,
            "page_end": 3,
            "is_official_policy": True,
        }
        steps = [{"finalize": {"response": "12 ngày.", "citations": [citation]}}]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("abc")]

        citation_events = [e for e in events if e["type"] == "citation"]
        assert citation_events == [
            {
                "type": "citation",
                "source": "doc.md",
                "title": "Chính sách nghỉ phép",
                "page_start": 3,
                "is_official_policy": True,
            }
        ]

    @pytest.mark.asyncio
    async def test_done_event_carries_escalate_and_ticket_draft(self):
        steps = [
            {
                "escalate_ticket": {
                    "response": "Đã tạo ticket.",
                    "escalate": True,
                    "escalate_reason": "low_confidence",
                    "query": "abc",
                    "ticket_category": "leave_policies",
                    "ticket_department": "HRBP",
                    "ticket_priority": "Medium",
                }
            }
        ]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("abc")]

        done = events[-1]
        assert done["type"] == "done"
        assert done["escalate"] is True
        assert done["ticket_draft"]["target_department"] == "HRBP"

    @pytest.mark.asyncio
    async def test_done_event_ticket_draft_none_when_not_escalated(self):
        steps = [{"finalize": {"response": "12 ngày.", "citations": []}}]
        with patch("src.agents.service.agent.astream", new=_fake_astream(steps)):
            events = [e async for e in astream_answer("abc")]

        assert events[-1]["ticket_draft"] is None
        assert events[-1]["answer"]["response"] == "12 ngày."
        assert events[-1]["answer"]["intent"] == "hr_question"

    @pytest.mark.asyncio
    async def test_error_during_graph_run_emits_error_event_and_stops(self):
        async def _broken_gen(state, **kwargs):
            yield {"router": {"intent": "hr_question"}}
            raise RuntimeError("gateway timeout")

        with patch("src.agents.service.agent.astream", new=_broken_gen):
            events = [e async for e in astream_answer("abc")]

        assert events[-1] == {"type": "error", "message": "RuntimeError: gateway timeout"}
        # Không có answer_delta/done nào lọt qua sau lỗi.
        assert not any(e["type"] in ("answer_delta", "done") for e in events)

    @pytest.mark.asyncio
    async def test_multiturn_clarification_flow_qa_085(self):
        """Kiểm thử luồng hội thoại 2 lượt cho qa_085:
        Lượt 1: Hỏi câu mơ hồ -> Trợ lý hỏi lại làm rõ (intent = ambiguous).
        Lượt 2: Người dùng chọn nhánh 'sau khi sinh' -> Trợ lý chuyển sang RAG (intent = hr_question) và trả về kết quả.
        """
        # Lượt 1: Câu hỏi mơ hồ
        state_turn1 = {
            "query": "Tôi muốn nghỉ thai sản thì làm thủ tục gì?",
            "intent": "ambiguous",
            "needs_clarification": True,
            "clarifying_question": "Bạn muốn hỏi thủ tục nghỉ thai sản trước khi sinh hay sau khi sinh?",
            "response": "Bạn muốn hỏi thủ tục nghỉ thai sản trước khi sinh hay sau khi sinh?",
            "citations": [],
            "escalate": False,
        }
        with patch("src.agents.service.agent.ainvoke", new=AsyncMock(return_value=state_turn1)):
            res_turn1 = await answer("Tôi muốn nghỉ thai sản thì làm thủ tục gì?", history=[])

        assert res_turn1.needs_clarification is True
        assert res_turn1.intent == "ambiguous"
        assert res_turn1.response == "Bạn muốn hỏi thủ tục nghỉ thai sản trước khi sinh hay sau khi sinh?"

        # Lượt 2: Người dùng trả lời làm rõ kèm history Lượt 1
        history = [
            {"role": "user", "content": "Tôi muốn nghỉ thai sản thì làm thủ tục gì?"},
            {"role": "assistant", "content": "Bạn muốn hỏi thủ tục nghỉ thai sản trước khi sinh hay sau khi sinh?"},
        ]
        state_turn2 = {
            "query": "sau khi sinh",
            "condensed_query": "Thủ tục nghỉ thai sản sau khi sinh gồm những giấy tờ gì và quy trình thế nào?",
            "intent": "hr_question",
            "needs_clarification": False,
            "confidence_score": 0.92,
            "response": "Hồ sơ hưởng chế độ thai sản sau khi sinh gồm: Giấy khai sinh/trích lục khai sinh, đơn đề nghị hưởng chế độ nộp cho phòng Nhân sự trong vòng 45 ngày kể từ ngày trở lại làm việc.",
            "citations": [_citation(title="Chính sách thai sản & nghỉ phép", source_file="07_chinh-sach-nghi-phep.md")],
            "escalate": False,
        }
        with patch("src.agents.service.agent.ainvoke", new=AsyncMock(return_value=state_turn2)):
            res_turn2 = await answer("sau khi sinh", history=history)

        assert res_turn2.needs_clarification is False
        assert res_turn2.intent == "hr_question"
        assert "Giấy khai sinh" in res_turn2.response
        assert len(res_turn2.citations) == 1
        assert res_turn2.citations[0].source_file == "07_chinh-sach-nghi-phep.md"
        assert res_turn2.confidence_score == 0.92


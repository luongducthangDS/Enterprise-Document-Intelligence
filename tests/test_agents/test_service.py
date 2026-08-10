from unittest.mock import AsyncMock, patch

import pytest

from src.agents.service import answer


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

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nodes.router import _get_router_system, clarify_node, direct_node, router_node
from src.config import get_settings


class TestRouterNode:
    def test_get_router_system_includes_internal_names(self):
        settings = get_settings()
        original = settings.internal_company_names
        try:
            settings.internal_company_names = ["v-nova", "vnova"]
            prompt = _get_router_system()
            assert "v-nova, vnova" in prompt
            assert "VinFast" not in prompt
        finally:
            settings.internal_company_names = original

    @pytest.mark.asyncio
    async def test_named_company_question_is_out_of_scope_before_llm(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock()) as llm:
            result = await router_node({"query": "Tôi là nhân viên VinFast, lương thưởng thế nào?"})

        assert result["intent"] == "out_of_scope_or_personal"
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_hybrid_question_skips_llm_router(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock()) as llm:
            result = await router_node({"query": "Chính sách làm việc Hybrid như thế nào?"})

        assert result["intent"] == "hr_question"
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_parses_valid_intent_from_llm_output(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")):
            result = await router_node({"query": "Tôi được nghỉ mấy ngày phép?"})
        assert result["intent"] == "hr_question"

    @pytest.mark.asyncio
    async def test_parses_intent_case_insensitively_with_extra_text(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="  Ambiguous.\n")):
            result = await router_node({"query": "Tôi muốn nghỉ"})
        assert result["intent"] == "ambiguous"

    @pytest.mark.asyncio
    async def test_unparseable_output_falls_back_to_hr_question(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="không rõ")):
            result = await router_node({"query": "abc"})
        assert result["intent"] == "hr_question"


class TestDirectNode:
    @pytest.mark.asyncio
    async def test_returns_llm_response_as_response(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="  Chào bạn!  ")):
            result = await direct_node({"query": "Chào bạn"})
        assert result["response"] == "Chào bạn!"


class TestClarifyNode:
    @pytest.mark.asyncio
    async def test_sets_needs_clarification_and_response(self):
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value="Bạn muốn hỏi về nghỉ phép năm hay nghỉ ốm?"),
        ):
            result = await clarify_node({"query": "Tôi muốn nghỉ"})
        assert result["needs_clarification"] is True
        assert result["clarifying_question"] == "Bạn muốn hỏi về nghỉ phép năm hay nghỉ ốm?"
        assert result["response"] == result["clarifying_question"]


class TestEscalationGuard:
    """Chốt chặn trước nhánh escalate — xem router._guard_escalation.

    Ba tầng: (1) không có dấu hiệu hỏi quy định -> escalate không tốn LLM,
    (2) personal rõ ràng -> escalate không tốn LLM, (3) ca khó -> verifier.
    """

    @pytest.mark.asyncio
    async def test_personal_question_escalates_without_verifier_call(self):
        """"Đơn của tôi duyệt chưa" không hỏi quy định nào cả -> dừng ở tầng 1."""
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value="out_of_scope_or_personal"),
        ) as llm:
            result = await router_node({"query": "Đơn xin nghỉ phép của tôi đã được duyệt chưa?"})

        assert result["intent"] == "out_of_scope_or_personal"
        assert llm.await_count == 1  # chỉ router, không gọi verifier

    @pytest.mark.asyncio
    async def test_obvious_personal_data_question_skips_verifier(self):
        """"Tôi còn bao nhiêu ngày phép" có chữ "bao nhiêu" nhưng khớp heuristic
        personal rõ ràng -> dừng ở tầng 2, không trả tiền cho verifier."""
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value="out_of_scope_or_personal"),
        ) as llm:
            result = await router_node({"query": "Tôi còn bao nhiêu ngày phép năm nay?"})

        assert result["intent"] == "out_of_scope_or_personal"
        assert llm.await_count == 1

    @pytest.mark.asyncio
    async def test_policy_question_with_personal_context_is_rescued(self):
        """Regression cho đúng nhóm câu mà fast router hay xếp nhầm: người hỏi
        tự cung cấp số liệu của mình nhưng thứ họ cần là quy định chung."""
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(side_effect=["out_of_scope_or_personal", "policy_answerable"]),
        ) as llm:
            result = await router_node({"query": "Cuối năm mình còn 8 ngày phép chưa dùng thì xử lý thế nào?"})

        assert result["intent"] == "hr_question"
        assert llm.await_count == 2

    @pytest.mark.asyncio
    async def test_verifier_can_confirm_escalation(self):
        """Câu phi-HR lọt tới tầng 3 vì cụm "làm thế nào" khớp policy signal —
        verifier xác nhận escalate. Đây là known verifier inefficiency (đo được
        1/140 câu, ~5-6s lãng phí), giữ nguyên có chủ đích: thêm heuristic
        "phi-HR" chỉ để cứu 0,7% traffic sẽ tạo false negative mới."""
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(side_effect=["out_of_scope_or_personal", "personal_data_required"]),
        ):
            result = await router_node(
                {"query": "Làm thế nào để fix lỗi NullReferenceException trong code C#?"}
            )

        assert result["intent"] == "out_of_scope_or_personal"

    @pytest.mark.asyncio
    async def test_guard_can_be_disabled(self):
        settings = get_settings()
        original = settings.escalation_guard_enabled
        try:
            settings.escalation_guard_enabled = False
            with patch(
                "src.agents.nodes.router.acall_llm",
                new=AsyncMock(return_value="out_of_scope_or_personal"),
            ) as llm:
                result = await router_node(
                    {"query": "Cuối năm mình còn 8 ngày phép chưa dùng thì xử lý thế nào?"}
                )
            assert result["intent"] == "out_of_scope_or_personal"
            assert llm.await_count == 1
        finally:
            settings.escalation_guard_enabled = original

    @pytest.mark.asyncio
    async def test_guard_does_not_touch_other_intents(self):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="ambiguous")) as llm:
            result = await router_node({"query": "Tôi muốn nghỉ 3 ngày tuần sau."})

        assert result["intent"] == "ambiguous"
        assert llm.await_count == 1


class TestVerifierTelemetry:
    """4 metric Ted yêu cầu (trigger_rate, useful_rate, latency, changed_route)
    đều tính được từ các trường này, nên chúng phải có mặt đúng lúc."""

    @pytest.mark.asyncio
    async def test_reports_verifier_not_called_when_heuristic_decides(self):
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value="out_of_scope_or_personal"),
        ):
            result = await router_node({"query": "Đơn xin nghỉ phép của tôi đã được duyệt chưa?"})

        assert result["verifier_called"] is False
        assert "verifier_latency_ms" not in result

    @pytest.mark.asyncio
    async def test_reports_changed_route_when_verifier_rescues(self):
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(side_effect=["out_of_scope_or_personal", "policy_answerable"]),
        ):
            result = await router_node({"query": "Cuối năm mình còn 8 ngày phép chưa dùng thì xử lý thế nào?"})

        assert result["intent"] == "hr_question"
        assert result["verifier_called"] is True
        assert result["verifier_changed_route"] is True
        assert isinstance(result["verifier_latency_ms"], int)

    @pytest.mark.asyncio
    async def test_reports_unchanged_route_when_verifier_confirms(self):
        """Đây là ca cần đếm được: verifier tốn tiền nhưng chỉ xác nhận điều đã
        rõ. Tỷ lệ này tăng = tín hiệu thêm pre-filter."""
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(side_effect=["out_of_scope_or_personal", "personal_data_required"]),
        ):
            result = await router_node(
                {"query": "Làm thế nào để fix lỗi NullReferenceException trong code C#?"}
            )

        assert result["verifier_called"] is True
        assert result["verifier_changed_route"] is False

    @pytest.mark.asyncio
    async def test_no_verifier_field_when_guard_not_reached(self):
        """Câu hr_question bình thường không đi qua guard -> không có trường
        telemetry nào, để trigger_rate không bị pha loãng sai mẫu số."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")):
            result = await router_node({"query": "Nghỉ phép năm được mấy ngày?"})

        assert "verifier_called" not in result

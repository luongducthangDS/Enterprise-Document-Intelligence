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
    @pytest.mark.parametrize(
        "query",
        [
            "Checkout Redesign dự kiến release khi nào?",
            "Checkout Redesign đang có blocker gì?",
            "Recommendation System hiện ở trạng thái nào?",
            "Kết quả experiment của Checkout Redesign là gì?",
        ],
    )
    async def test_explicit_product_question_skips_llm_router(self, query):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock()) as llm:
            result = await router_node({"query": query})

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
            result = await router_node({"query": "Quy định số ngày nghỉ phép năm của công ty"})
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
        """Verifier được gọi khi câu có business signal + policy signal nhưng LLM xác nhận personal_data_required."""
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(side_effect=["out_of_scope_or_personal", "personal_data_required"]),
        ):
            result = await router_node(
                {"query": "Quy chế khen thưởng định kỳ của công ty được tính thế nào?"}
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


class TestSimpleGreetingFastPath:
    """Kiểm tra fast-path cho câu chào hỏi thuần túy (≤ 5 từ) không gọi LLM Router."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Chào bạn",
            "Xin chào",
            "Xin chào bạn",
            "Hello",
            "Hi",
            "Hey",
            "Cảm ơn nhé",
            "Ok cảm ơn",
            "Cảm ơn bạn nhiều",
            "Thanks",
            "Bye",
            "Tạm biệt",
            "Tạm biệt nhé",
        ],
    )
    async def test_simple_greetings_skip_llm_router(self, query):
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock()) as llm:
            result = await router_node({"query": query})

        assert result["intent"] == "greeting"
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_greeting_with_business_question_does_not_fast_route(self):
        """Câu chào kèm câu hỏi nghiệp vụ không bị bắt nhầm bởi greeting regex."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")) as llm:
            result = await router_node({"query": "Chào bạn, cho mình hỏi chính sách nghỉ phép năm thế nào?"})

        assert result["intent"] == "hr_question"
        llm.assert_called_once()


class TestWhitelistGuard:
    """Kiểm tra Whitelist Guard: word-boundary, case-sensitive acronyms và shadow/live mode."""

    def test_word_boundary_avoids_vietnamese_accent_collision(self):
        from src.agents.nodes.router import _has_any_business_signal

        # "vui" chứa "ui", "tốt" chứa "ot", "vất vả" chứa "vat" sau khi bỏ dấu
        # Nhờ word-boundary (\b) và lọc acronym ngắn, câu này KHÔNG được nhận là có signal
        assert _has_any_business_signal("Hôm nay tôi rất vui, thời tiết tốt") is False
        assert _has_any_business_signal("Công việc hôm nay vất vả quá") is False
        assert _has_any_business_signal("Thời tiết Hà Nội hôm nay thế nào?") is False
        assert _has_any_business_signal("Học lập trình Python từ đâu?") is False
        assert _has_any_business_signal("Nấu món phở bò truyền thống") is False

    def test_case_sensitive_acronyms_detected(self):
        from src.agents.nodes.router import _has_any_business_signal

        # Các acronym nghiệp vụ quan trọng khi viết hoa được nhận diện chính xác
        assert _has_any_business_signal("Quy định tính thuế VAT thế nào?") is True
        assert _has_any_business_signal("Làm thêm giờ OT tính lương ra sao?") is True
        assert _has_any_business_signal("Tài liệu API thanh toán nằm ở đâu?") is True
        assert _has_any_business_signal("Hướng dẫn thiết kế UI/UX theo chuẩn") is True

    def test_business_terms_detected_with_word_boundary(self):
        from src.agents.nodes.router import _has_any_business_signal

        assert _has_any_business_signal("Chính sách nghỉ phép năm là bao nhiêu ngày?") is True
        assert _has_any_business_signal("Quy định tạm ứng chi phí công tác") is True
        assert _has_any_business_signal("Báo cáo tài chính quý 3 nộp khi nào?") is True
        assert _has_any_business_signal("Checkout redesign khi nào release?") is True
        assert _has_any_business_signal("Thời gian thử việc tối đa theo luật?") is True

    @pytest.mark.asyncio
    async def test_shadow_mode_logs_and_marks_state_without_blocking(self):
        """Shadow mode: câu không có signal vẫn được chuyển xuống LLM nhưng state có whitelist_shadow_would_block."""
        settings = get_settings()
        original = settings.whitelist_guard_shadow
        try:
            settings.whitelist_guard_shadow = True
            with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="out_of_scope_or_personal")) as llm:
                result = await router_node({"query": "Học lập trình Python thế nào?"})

            assert result["intent"] == "out_of_scope_or_personal"
            assert result.get("whitelist_shadow_would_block") is True
            assert result.get("whitelist_blocked") is not True
            llm.assert_called_once()
        finally:
            settings.whitelist_guard_shadow = original

    @pytest.mark.asyncio
    async def test_live_mode_blocks_immediately_without_llm(self):
        """Live mode (whitelist_guard_shadow=False): câu không có signal bị từ chối ngay 0ms, không gọi LLM."""
        settings = get_settings()
        original = settings.whitelist_guard_shadow
        try:
            settings.whitelist_guard_shadow = False
            with patch("src.agents.nodes.router.acall_llm", new=AsyncMock()) as llm:
                result = await router_node({"query": "Học lập trình Python thế nào?"})

            assert result["intent"] == "out_of_scope_or_personal"
            assert result.get("whitelist_blocked") is True
            assert result.get("verifier_called") is False
            llm.assert_not_called()
        finally:
            settings.whitelist_guard_shadow = original


class TestGuardTier0:
    """Tier-0 trong _guard_escalation: chặn các câu không có business signal trước khi gọi LLM Verifier."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Nấu phở bò truyền thống mất bao lâu?",
            "Đi du lịch Đà Lạt cần chuẩn bị những gì?",
        ],
    )
    async def test_tier0_skips_verifier_for_non_business_query(self, query):
        """Khi shadow mode bật: router LLM vẫn gọi (1 lần), nhưng Tier-0 trong guard chặn không gọi LLM Verifier."""
        settings = get_settings()
        original = settings.whitelist_guard_shadow
        try:
            settings.whitelist_guard_shadow = True
            with patch(
                "src.agents.nodes.router.acall_llm",
                new=AsyncMock(return_value="out_of_scope_or_personal"),
            ) as llm:
                result = await router_node({"query": query})

            assert result["intent"] == "out_of_scope_or_personal"
            assert result.get("verifier_called") is False
            # Chỉ gọi router LLM (ở shadow mode), KHÔNG gọi verifier LLM
            assert llm.await_count == 1
        finally:
            settings.whitelist_guard_shadow = original


class TestG3Regression:
    """Kiểm thử hồi quy cho 5 test cases thuộc Bug G3 (G3_ROUTER_FALSE_AMBIGUOUS).

    Đảm bảo Router phân loại chính xác các trường hợp mơ hồ (ambiguous) và
    không bị nhầm lẫn giữa out_of_scope_or_personal, hr_question và ambiguous.
    """

    def test_router_system_contains_g3_clarification_rules(self):
        prompt = _get_router_system()
        # qa_082: ngày phép tiêu chuẩn vs cộng dồn
        assert "Tôi còn bao nhiêu ngày phép?" in prompt
        # qa_083: hợp đồng sau thử việc vs gia hạn
        assert "Tôi khi nào được ký hợp đồng mới?" in prompt
        # qa_085: thủ tục thai sản trước sinh vs sau sinh
        assert "Tôi muốn nghỉ thai sản thì làm thủ tục gì?" in prompt
        # qa_086: thiếu lương cơ bản vs thưởng vs khấu trừ
        assert "Lương của tôi tháng này bị thiếu." in prompt
        # qa_111: bảo hiểm sức khỏe người thân
        assert "Đăng ký bảo hiểm sức khỏe cho vợ con" in prompt or "bảo hiểm người thân" in prompt

    @pytest.mark.asyncio
    async def test_qa_082_leave_balance_ambiguity_returns_ambiguous(self):
        """qa_082: 'Tôi còn bao nhiêu ngày phép?' mập mờ giữa phép năm nay và dồn năm trước -> ambiguous."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="ambiguous")) as llm:
            result = await router_node({"query": "Tôi còn bao nhiêu ngày phép?"})
        assert result["intent"] == "ambiguous"
        assert llm.await_count == 1

    @pytest.mark.asyncio
    async def test_qa_083_new_contract_timing_ambiguity_returns_ambiguous(self):
        """qa_083: 'Tôi khi nào được ký hợp đồng mới?' mập mờ giữa sau thử việc và gia hạn -> ambiguous."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="ambiguous")) as llm:
            result = await router_node({"query": "Tôi khi nào được ký hợp đồng mới?"})
        assert result["intent"] == "ambiguous"
        assert llm.await_count == 1

    @pytest.mark.asyncio
    async def test_qa_085_maternity_procedure_ambiguity_returns_ambiguous(self):
        """qa_085: 'Tôi muốn nghỉ thai sản thì làm thủ tục gì?' mập mờ trước sinh vs sau sinh -> ambiguous."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="ambiguous")) as llm:
            result = await router_node({"query": "Tôi muốn nghỉ thai sản thì làm thủ tục gì?"})
        assert result["intent"] == "ambiguous"
        assert llm.await_count == 1

    @pytest.mark.asyncio
    async def test_qa_086_missing_salary_ambiguity_returns_ambiguous(self):
        """qa_086: 'Lương của tôi tháng này bị thiếu.' mập mờ giữa thiếu lương cơ bản, thưởng, phụ cấp -> ambiguous."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="ambiguous")) as llm:
            result = await router_node({"query": "Lương của tôi tháng này bị thiếu."})
        assert result["intent"] == "ambiguous"
        assert llm.await_count == 1

    @pytest.mark.asyncio
    async def test_qa_111_dependent_health_insurance_returns_hr_question(self):
        """qa_111: 'Em muốn đăng ký bảo hiểm sức khỏe cho vợ và 2 con thì chi phí thế nào và gói bảo hiểm sẽ ở hạng nào?' -> hr_question."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")) as llm:
            result = await router_node({
                "query": "Em muốn đăng ký bảo hiểm sức khỏe cho vợ và 2 con thì chi phí thế nào và gói bảo hiểm sẽ ở hạng nào?"
            })
        assert result["intent"] == "hr_question"
        assert llm.await_count == 1

    @pytest.mark.asyncio
    async def test_clarified_maternity_procedure_routes_to_hr_question(self):
        """Sau khi làm rõ, 'Thủ tục nghỉ thai sản sau khi sinh gồm những giấy tờ gì?' phải được phân loại là hr_question."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")) as llm:
            result = await router_node({"condensed_query": "Thủ tục nghỉ thai sản sau khi sinh gồm những giấy tờ gì?"})
        assert result["intent"] == "hr_question"
        assert llm.await_count == 1

    @pytest.mark.asyncio
    async def test_clarified_leave_balance_routes_to_hr_question(self):
        """Sau khi làm rõ, 'Quy định số ngày phép năm nay được mấy ngày?' phải được phân loại là hr_question."""
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock(return_value="hr_question")) as llm:
            result = await router_node({"condensed_query": "Quy định số ngày phép năm nay được mấy ngày?"})
        assert result["intent"] == "hr_question"
        assert llm.await_count == 1


class TestChitChatFastPath:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "bạn là ai",
            "bạn tên gì",
            "bạn thông minh quá",
            "bot ơi",
            "bạn có khỏe không",
            "bạn nghĩ sao",
            "hay đấy",
            "giỏi thật",
        ],
    )
    async def test_chit_chat_fast_path_returns_greeting(self, query):
        from src.agents.nodes.router import condense_and_route_node
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock()) as llm:
            result = await condense_and_route_node({"query": query})
        assert result["intent"] == "greeting"
        llm.assert_not_called()


class TestCapabilityDiscoveryFastPath:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "tôi có thể hỏi gì",
            "tôi có thể hỏi những gì",
            "bạn có thể làm gì",
            "bạn có thể giúp gì",
            "bạn giúp được gì",
            "bạn làm được gì",
            "bạn hỗ trợ gì",
            "bạn biết gì",
            "bạn có khả năng gì",
            "các chủ đề bạn hỗ trợ",
        ],
    )
    async def test_capability_queries_return_capability_discovery(self, query):
        from src.agents.nodes.router import condense_and_route_node
        with patch("src.agents.nodes.router.acall_llm", new=AsyncMock()) as llm:
            result = await condense_and_route_node({"query": query})
        assert result["intent"] == "capability_discovery"
        llm.assert_not_called()


class TestCapabilityDiscoveryNoFalsePositive:
    """Đảm bảo câu hỏi nghiệp vụ thật KHÔNG bị Capability tier nuốt nhầm."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Cho tôi mẫu đơn xin nghỉ phép",
            "Hướng dẫn quy trình xin nghỉ phép thế nào?",
            "Cho tôi ví dụ về chính sách phúc lợi",
            "Bên mình hỗ trợ những khoản phụ cấp gì?",
            "bạn có biết quy định nghỉ thai sản không",
        ],
    )
    async def test_business_query_not_captured_by_capability(self, query):
        from src.agents.nodes.router import condense_and_route_node
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value='{"condensed_query": "...", "intent": "hr_question", "clarifying_question": null}'),
        ):
            result = await condense_and_route_node({"query": query})
        assert result.get("intent") != "capability_discovery", (
            f"Business query was wrongly captured by capability tier: {query!r}"
        )


class TestChitChatNoFalsePositive:
    """Đảm bảo câu hỏi follow-up ngắn không bị chit-chat tier nhận nhầm."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Thế nào?",
            "Vậy thế nào rồi?",
        ],
    )
    async def test_short_followup_not_fast_pathed_as_greeting(self, query):
        from src.agents.nodes.router import condense_and_route_node
        result = await condense_and_route_node({"query": query})
        # Không có business signal -> whitelist guard block, nhưng KHÔNG được fast-path thành greeting
        assert result.get("intent") != "greeting"


class TestCapabilityNode:
    @pytest.mark.asyncio
    async def test_capability_node_returns_template_and_quick_prompts(self):
        from src.agents.nodes.router import capability_node
        result = await capability_node({"intent": "capability_discovery"})
        assert "response" in result
        assert "HR & Nhân sự" in result["response"]
        assert "Kế toán & Tài chính" in result["response"]
        assert "Product & Tech" in result["response"]
        assert len(result.get("quick_prompts", [])) >= 3



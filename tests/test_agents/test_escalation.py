import pytest

from src.agents.nodes.escalation import (
    TICKET_ROUTING_PATH,
    _match_routing_rule,
    _mentions_competitor_company,
    _requires_personal_data,
    _strip_diacritics,
    confidence_node,
    escalate_node,
)
from src.config import get_settings


class TestStripDiacritics:
    def test_strips_common_vietnamese_diacritics(self):
        assert _strip_diacritics("lương") == "luong"
        assert _strip_diacritics("thuế TNCN") == "thue TNCN"

    def test_handles_dd_specially(self):
        # đ/Đ không decompose qua NFD như các ký tự có dấu khác — cần map riêng.
        assert _strip_diacritics("Đơn xin nghỉ phép") == "Don xin nghi phep"

    def test_ascii_text_unchanged(self):
        assert _strip_diacritics("OT bhxh") == "OT bhxh"


class TestMatchRoutingRule:
    def test_versioned_routing_config_exists_outside_gitignored_data(self):
        assert TICKET_ROUTING_PATH.is_absolute()
        assert TICKET_ROUTING_PATH.is_file()
        assert "resources" in TICKET_ROUTING_PATH.parts

    def test_matches_compensation_keyword_with_diacritics(self):
        rule = _match_routing_rule("Lương của tôi tháng này bị trừ, tại sao vậy?")
        assert rule["target_department"] == "CB"
        assert rule["category"] == "compensation_policies"

    def test_matches_employee_relations_keyword(self):
        rule = _match_routing_rule("Tôi muốn khiếu nại về cách quản lý đối xử với tôi.")
        assert rule["target_department"] == "ER"
        assert rule["category"] == "employee_relations"

    def test_falls_back_to_unmatched_hrbp(self):
        rule = _match_routing_rule("Hôm nay thời tiết thế nào?")
        assert rule["category"] == "unmatched"
        assert rule["target_department"] == "HRBP"

    def test_higher_priority_rule_wins_when_multiple_departments_match(self):
        rule = _match_routing_rule("Tôi bị quấy rối và còn bị trừ lương.")
        assert rule["target_department"] == "ER"
        assert rule["ticket_priority"] == "High"


class TestPersonalDataDetection:
    def test_detects_personal_leave_balance(self):
        assert _requires_personal_data("Tôi còn bao nhiêu ngày phép năm nay?") is True

    def test_does_not_treat_general_policy_as_personal_data(self):
        assert _requires_personal_data("Nhân viên được bao nhiêu ngày phép năm?") is False


class TestConfidenceNode:
    def test_no_chunks_gives_zero_confidence_and_escalates(self):
        result = confidence_node({"retrieved_chunks": [], "hallucination_passed": True})
        assert result["confidence_score"] == 0.0
        assert result["escalate"] is True
        assert result["escalate_reason"] == "low_confidence"

    def test_close_chunk_and_passed_check_gives_high_confidence(self):
        state = {
            "retrieved_chunks": [{"distance": 0.1, "score": None}, {"distance": 0.3, "score": None}],
            "hallucination_passed": True,
        }
        result = confidence_node(state)
        assert result["confidence_score"] == 1.0
        assert "escalate" not in result

    def test_uses_rerank_score_when_available(self):
        """Reranker cho điểm 0-1 trải rộng (đo thực tế: 0.96 cho đoạn trả lời
        đúng, 0.009 cho đoạn lạc đề) nên dùng trực tiếp làm confidence."""
        state = {
            "retrieved_chunks": [{"distance": 0.11, "score": 0.92}, {"distance": 0.10, "score": 0.20}],
            "hallucination_passed": True,
        }
        result = confidence_node(state)
        assert result["confidence_score"] == 0.92
        assert "escalate" not in result

    def test_low_rerank_score_escalates_even_when_distance_is_small(self):
        """Regression: distance cosine thực tế chỉ dao động 0.10-0.23 nên công
        thức cũ `1 - distance` luôn cho ra >= 0.77 và KHÔNG BAO GIỜ chạm ngưỡng
        escalate — nhánh escalate vì confidence thấp coi như đã chết."""
        state = {
            "retrieved_chunks": [{"distance": 0.12, "score": 0.06}],
            "hallucination_passed": True,
        }
        result = confidence_node(state)
        assert result["confidence_score"] == 0.06
        assert result["escalate"] is True
        assert result["escalate_reason"] == "low_confidence"

    def test_failed_hallucination_check_caps_confidence_low(self):
        """Regression: cap phải luôn nằm DƯỚI low_confidence_threshold. Cap cũ
        là hằng số 0.3 hợp lệ với ngưỡng 0.5, nhưng khi hạ ngưỡng xuống 0.2 thì
        0.3 > 0.2 nên hallucination fail hết escalate mà không ai thấy."""
        state = {"retrieved_chunks": [{"distance": 0.05}], "hallucination_passed": False}
        result = confidence_node(state)
        assert result["confidence_score"] < get_settings().low_confidence_threshold
        assert result["escalate"] is True

    def test_unanswerable_context_escalates_despite_high_rerank_score(self):
        """Nhóm lỗi nguy hiểm nhất đo được: reranker cho 0.78-1.00 cho đoạn KHÔNG
        chứa câu trả lời, nên không ngưỡng nào trên score bắt được. Tín hiệu duy
        nhất dùng được là chính model đọc context và báo không đủ thông tin."""
        state = {
            "retrieved_chunks": [{"distance": 0.11, "score": 0.98}],
            "hallucination_passed": True,
            "answerable": False,
        }
        result = confidence_node(state)
        assert result["confidence_score"] < get_settings().low_confidence_threshold
        assert result["escalate"] is True
        assert result["escalate_reason"] == "low_confidence"

    def test_answerable_defaults_true_so_old_states_are_unaffected(self):
        state = {"retrieved_chunks": [{"distance": 0.11, "score": 0.98}], "hallucination_passed": True}
        result = confidence_node(state)
        assert result["confidence_score"] == 0.98
        assert "escalate" not in result


class TestEscalateNode:
    def test_out_of_scope_intent_routes_to_matched_department(self):
        state = {"query": "Lương của Nguyễn Văn A là bao nhiêu?", "intent": "out_of_scope_or_personal"}
        result = escalate_node(state)
        assert result["escalate"] is True
        assert result["escalate_reason"] == "out_of_scope"
        assert result["ticket_department"] == "CB"
        # Response KHÔNG còn nêu mã phòng ban nội bộ và không được nói đã gửi
        # cho bộ phận nào — hệ thống chưa tích hợp với HR thật. Người phụ trách
        # user-facing đến từ boundary decision (xem tests/test_agents/test_boundary.py).
        assert "đã gửi" not in result["response"].lower()
        assert "đã tạo yêu cầu hỗ trợ gửi" not in result["response"].lower()

    def test_low_confidence_keeps_existing_escalate_reason(self):
        state = {"query": "Câu hỏi không rõ ràng", "intent": "hr_question", "escalate_reason": "low_confidence"}
        result = escalate_node(state)
        assert result["escalate_reason"] == "low_confidence"

    def test_employee_relations_gets_high_priority(self):
        state = {"query": "Tôi bị quấy rối ở công ty", "intent": "hr_question"}
        result = escalate_node(state)
        assert result["ticket_department"] == "ER"
        assert result["ticket_priority"] == "High"

    def test_competitor_question_declines_without_creating_ticket(self):
        state = {
            "query": "Viettel cấp bao nhiêu ngày nghỉ phép năm cho nhân viên mới thử việc?",
            "intent": "out_of_scope_or_personal",
        }
        result = escalate_node(state)
        assert result["escalate"] is False
        assert result["escalate_reason"] == "competitor_question"
        assert "ticket_department" not in result
        assert "phạm vi demo" in result["response"]

    def test_competitor_detection_is_diacritic_insensitive(self):
        state = {"query": "Samsung Electronics Vietnam trả lương bao nhiêu?", "intent": "out_of_scope_or_personal"}
        result = escalate_node(state)
        assert result["escalate_reason"] == "competitor_question"

    def test_vinfast_reference_declines_without_ticket_by_default(self):
        state = {
            "query": "Tôi là nhân viên VinFast, lương thưởng thế nào?",
            "intent": "out_of_scope_or_personal",
        }
        result = escalate_node(state)
        assert result["escalate"] is False
        assert result["escalate_reason"] == "competitor_question"
        assert "ticket_department" not in result

    def test_personal_data_question_without_company_name_still_escalates_ticket(self):
        state = {"query": "Tôi còn bao nhiêu ngày phép năm nay?", "intent": "out_of_scope_or_personal"}
        result = escalate_node(state)
        assert result["escalate"] is True
        assert result["escalate_reason"] == "personal_data_required"


class TestCompetitorCompanyDetection:
    """Rule chặn câu hỏi chính sách của công ty khác — xét QUAN HỆ NGỮ CẢNH,
    không phải substring. Xem docstring _mentions_competitor_company."""

    @pytest.mark.parametrize(
        "query",
        [
            # Regression qa_006 (in_scope): Grab là phương tiện đi lại, câu hỏi
            # vẫn là hỏi định mức công tác phí của công ty mình.
            "Đi công tác nếu dùng taxi hoặc Grab di chuyển trong ngày thì được thanh toán tối đa bao nhiêu?",
            "Mua hàng trên Shopee có được hoàn thuế không?",
            "Đặt vé qua MoMo có được thanh toán không?",
            "Thanh toán bằng MoMo có được hoàn ứng không?",
        ],
    )
    def test_company_name_as_vendor_is_not_competitor_question(self, query):
        assert _mentions_competitor_company(query) is False

    @pytest.mark.parametrize(
        "query",
        [
            "Grab Việt Nam có trả thưởng KPI hàng quý cho tài xế đối tác không?",
            "Viettel cấp bao nhiêu ngày nghỉ phép năm cho nhân viên mới thử việc?",
            "Cho mình hỏi mức thưởng Tết 2024 của nhân viên FPT Software là bao nhiêu tháng lương?",
            "Chính sách của Viettel ra sao?",
            "Nhân viên Tiki được nghỉ mấy ngày?",
            "Tôi làm việc tại FPT thì sao?",
        ],
    )
    def test_company_name_as_subject_is_competitor_question(self, query):
        assert _mentions_competitor_company(query) is True

    def test_internal_company_is_never_competitor(self):
        assert _mentions_competitor_company("Chính sách nghỉ phép của V-NOVA thế nào?") is False

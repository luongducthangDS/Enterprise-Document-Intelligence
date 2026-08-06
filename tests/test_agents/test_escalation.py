from src.agents.nodes.escalation import _match_routing_rule, _strip_diacritics, confidence_node, escalate_node


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


class TestConfidenceNode:
    def test_no_chunks_gives_zero_confidence_and_escalates(self):
        result = confidence_node({"retrieved_chunks": [], "hallucination_passed": True})
        assert result["confidence_score"] == 0.0
        assert result["escalate"] is True
        assert result["escalate_reason"] == "low_confidence"

    def test_close_chunk_and_passed_check_gives_high_confidence(self):
        state = {
            "retrieved_chunks": [{"distance": 0.1}, {"distance": 0.3}],
            "hallucination_passed": True,
        }
        result = confidence_node(state)
        assert result["confidence_score"] == 0.9
        assert "escalate" not in result

    def test_failed_hallucination_check_caps_confidence_low(self):
        state = {"retrieved_chunks": [{"distance": 0.05}], "hallucination_passed": False}
        result = confidence_node(state)
        assert result["confidence_score"] <= 0.3
        assert result["escalate"] is True


class TestEscalateNode:
    def test_out_of_scope_intent_routes_to_matched_department(self):
        state = {"query": "Lương của Nguyễn Văn A là bao nhiêu?", "intent": "out_of_scope_or_personal"}
        result = escalate_node(state)
        assert result["escalate"] is True
        assert result["escalate_reason"] == "out_of_scope"
        assert result["ticket_department"] == "CB"
        assert "CB" in result["response"]

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
        assert "công ty khác" in result["response"]

    def test_competitor_detection_is_diacritic_insensitive(self):
        state = {"query": "Samsung Electronics Vietnam trả lương bao nhiêu?", "intent": "out_of_scope_or_personal"}
        result = escalate_node(state)
        assert result["escalate_reason"] == "competitor_question"

    def test_personal_data_question_without_company_name_still_escalates_ticket(self):
        state = {"query": "Tôi còn bao nhiêu ngày phép năm nay?", "intent": "out_of_scope_or_personal"}
        result = escalate_node(state)
        assert result["escalate"] is True
        assert result["escalate_reason"] == "out_of_scope"

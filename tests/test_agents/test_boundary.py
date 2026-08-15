"""Boundary engine: khớp scenario, cắt trần action, và các nhánh không được phép."""

import pytest

from src.agents.boundary import (
    cap_action,
    decision_for_scenario,
    is_field_allowed,
    load_registry,
    match_scenario,
    resolve_boundary,
)
from src.agents.nodes.boundary import boundary_node
from src.agents.nodes.escalation import escalate_node


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("Nghỉ phép năm được bao nhiêu ngày phép?", 1),
        ("Mình muốn tạo đơn nghỉ phép thì làm sao?", 2),
        ("Quên chấm công hôm qua thì xử lý thế nào?", 11),
        ("Tháng này lương thiếu tháng này của em, kiểm tra giúp", 20),
        ("Em bị quấy rối ở chỗ làm thì báo ai?", 52),
        ("Cho hỏi chính sách khiếu nại của công ty", 53),
        ("Có tai nạn lao động ở xưởng thì báo thế nào?", 58),
    ],
)
def test_match_scenario_maps_known_queries(query, expected_id):
    assert match_scenario(query) == expected_id


def test_unmatched_query_returns_none_instead_of_guessing():
    assert match_scenario("hôm nay trời đẹp quá nhỉ") is None


def test_fallback_decision_does_not_invent_owner_for_answer_branch():
    decision = resolve_boundary("hôm nay trời đẹp quá nhỉ", "hr_question")
    assert decision.resolution == "fallback"
    assert decision.scenario_id is None
    assert decision.runtime_action == "NONE"
    assert decision.handoff_target is None


def test_fallback_for_out_of_scope_routes_to_directory_owner():
    decision = resolve_boundary("đơn của tôi duyệt chưa", "out_of_scope_or_personal")
    assert decision.resolution == "fallback"
    assert decision.runtime_action == "LINK_ONLY"
    assert decision.handoff_target is not None
    assert decision.handoff_target["code"] == "HR_OPS"


def test_create_case_scenario_is_capped_to_draft_in_mvp1():
    decision = decision_for_scenario(20)
    assert decision.max_runtime_action == "CREATE_CASE"
    assert decision.runtime_action == "PREFILL_DRAFT"
    assert decision.user_facing_action_label == "Chuẩn bị yêu cầu"


def test_cap_action_never_exceeds_mvp1_ceiling():
    assert cap_action("CREATE_CASE") == "PREFILL_DRAFT"
    assert cap_action("LINK_ONLY") == "LINK_ONLY"
    assert cap_action("NONE") == "NONE"


def test_link_only_scenario_never_exposes_draft_label():
    decision = decision_for_scenario(19)
    assert decision.runtime_action == "LINK_ONLY"
    assert decision.user_facing_action_label == "Hướng dẫn gửi"


def test_not_available_source_is_labelled_as_no_access():
    decision = decision_for_scenario(54)
    assert decision.runtime_source_status == "NOT_AVAILABLE"
    assert "chưa có" in decision.source_of_truth_label.lower()
    assert decision.runtime_action == "LINK_ONLY"


def test_allowed_data_fields_are_an_allowlist():
    assert is_field_allowed(21, "bank_account_last4") is True
    # Registry chỉ cho 4 số cuối; số tài khoản đầy đủ không tồn tại như một field.
    assert is_field_allowed(21, "bank_account_full") is False
    assert is_field_allowed(None, "leave_type") is False


def test_sensitive_scenarios_require_no_field_before_handoff():
    for scenario_id in (52, 54, 57, 58):
        decision = decision_for_scenario(scenario_id)
        assert all(not field["required_for_prefill"] for field in decision.allowed_data_fields)


def test_boundary_node_attaches_decision_to_state():
    result = boundary_node({"query": "Nghỉ phép năm được bao nhiêu ngày phép?", "intent": "hr_question"})
    assert result["boundary"]["scenario_id"] == 1
    assert result["boundary"]["assistant_role"] == "ANSWER"


def test_escalate_node_does_not_create_ticket_for_human_first_scenario():
    state = {
        "query": "Em bị quấy rối ở chỗ làm thì báo ai?",
        "intent": "out_of_scope_or_personal",
        "boundary": decision_for_scenario(52).to_dict(),
    }
    result = escalate_node(state)
    assert result["escalate"] is False
    assert result["escalate_reason"] == "human_first_required"
    assert "Employee Relations" in result["response"]


def test_escalate_node_response_never_claims_a_submitted_request():
    state = {
        "query": "đơn của tôi duyệt chưa",
        "intent": "out_of_scope_or_personal",
        "boundary": resolve_boundary("đơn của tôi duyệt chưa", "out_of_scope_or_personal").to_dict(),
    }
    result = escalate_node(state)
    assert result["escalate"] is True
    for claim in ("đã gửi", "đã tạo yêu cầu", "HR đã nhận"):
        assert claim.lower() not in result["response"].lower()


def test_every_scenario_produces_a_decision():
    registry = load_registry()
    for scenario in registry["scenarios"]:
        decision = decision_for_scenario(scenario["id"])
        assert decision.assistant_role in registry["enums"]["assistant_role"]
        assert decision.runtime_action in ("NONE", "LINK_ONLY", "PREFILL_DRAFT")
        assert decision.handoff_target is not None or decision.assistant_role == "ANSWER"

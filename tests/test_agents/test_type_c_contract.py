"""NexaTech Type-C contract v3.1.0 (frozen) — tri-state runtime + pure_statutory
routing. Xem nexatech_agent_type_c_contract_v3.1.yaml (root repo) cho spec gốc.

File này test các đơn vị logic KHÔNG cần gọi LLM/Chroma thật (mocked/pure
function) — 20 canonical case + kịch bản A-F chạy sống được đo riêng qua
eval/scripts (xem báo cáo trong PR/commit), vì đây là live integration tốn API,
không phù hợp chạy trong pytest suite mặc định (cùng convention với
eval_agent.py tách khỏi tests/).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.boundary import resolve_boundary
from src.agents.graph import route_by_intent
from src.agents.nodes.escalation import OUT_OF_SCOPE_RESPONSE, out_of_scope_node
from src.agents.nodes.router import _get_router_system, router_node
from src.agents.service import _derive_runtime_state
from src.ingestion.metadata import RegistryRow, rag_eligible_rows
from src.models.schemas import AgentAnswer


class TestRouterPromptCoversPureStatutory:
    def test_prompt_declares_five_categories_and_internal_override(self):
        prompt = _get_router_system()
        assert "pure_statutory" in prompt
        assert "internal override" in prompt.lower()
        assert "5 từ trên" in prompt or "5 nhóm" in prompt

    @pytest.mark.asyncio
    async def test_router_classifies_pure_statutory_from_llm_output(self):
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value="pure_statutory"),
        ):
            result = await router_node(
                {"query": "Nghị định 293/2025/NĐ-CP quy định mức lương tối thiểu Vùng I là bao nhiêu?"}
            )
        assert result["intent"] == "pure_statutory"

    @pytest.mark.asyncio
    async def test_pure_statutory_does_not_trigger_escalation_guard(self):
        """pure_statutory là intent riêng, KHÔNG đi qua _guard_escalation (chỉ
        áp dụng cho out_of_scope_or_personal) — chỉ 1 lệnh gọi LLM (router),
        không có verifier thứ hai."""
        with patch(
            "src.agents.nodes.router.acall_llm",
            new=AsyncMock(return_value="pure_statutory"),
        ) as llm:
            result = await router_node({"query": "Điều 112 Bộ luật Lao động quy định gì?"})
        assert result["intent"] == "pure_statutory"
        assert llm.await_count == 1
        assert "verifier_called" not in result


class TestGraphRoutesPureStatutoryBeforeRetrieval:
    def test_route_by_intent_sends_pure_statutory_to_out_of_scope_node(self):
        assert route_by_intent({"intent": "pure_statutory"}) == "out_of_scope"

    def test_route_by_intent_unaffected_for_existing_intents(self):
        assert route_by_intent({"intent": "hr_question"}) == "retrieve"
        assert route_by_intent({"intent": "out_of_scope_or_personal"}) == "escalate"
        assert route_by_intent({"intent": "greeting"}) == "direct"
        assert route_by_intent({"intent": "ambiguous"}) == "clarify"


class TestOutOfScopeNode:
    def test_returns_fixed_template_no_ticket_no_citations(self):
        result = out_of_scope_node({"query": "Điều 112 Bộ luật Lao động quy định gì?"})
        assert result["response"] == OUT_OF_SCOPE_RESPONSE
        assert result["escalate"] is False
        assert result["citations"] == []

    def test_template_matches_contract_verbatim_markers(self):
        assert OUT_OF_SCOPE_RESPONSE.startswith("[OUT_OF_SCOPE]")
        assert "NexaBot" in OUT_OF_SCOPE_RESPONSE
        assert "NexaTech" in OUT_OF_SCOPE_RESPONSE


class TestBoundaryHandlesPureStatutory:
    def test_unmatched_pure_statutory_uses_conservative_fallback(self):
        decision = resolve_boundary("Điều 112 Bộ luật Lao động quy định gì?", "pure_statutory")
        assert decision.assistant_role == "PREPARE_AND_HANDOFF"
        assert decision.max_runtime_action == "LINK_ONLY"
        assert decision.resolution == "fallback"


class TestDeriveRuntimeState:
    def test_pure_statutory_intent_is_out_of_scope_regardless_of_other_fields(self):
        state, reason = _derive_runtime_state({"intent": "pure_statutory"})
        assert (state, reason) == ("OUT_OF_SCOPE", None)

    @pytest.mark.parametrize(
        "escalate_reason,expected_reason_code",
        [
            ("personal_data_required", "requires_live_personal_data"),
            ("user_requested_human", "requires_live_personal_data"),
            ("human_first_required", "requires_live_personal_data"),
            ("low_confidence", "missing_policy_evidence"),
            ("out_of_scope", "missing_policy_evidence"),
            ("competitor_question", "missing_policy_evidence"),
        ],
    )
    def test_escalate_reason_maps_to_contract_reason_code(self, escalate_reason, expected_reason_code):
        state, reason = _derive_runtime_state({"escalate_reason": escalate_reason, "escalate": True})
        assert (state, reason) == ("ABSTAIN", expected_reason_code)

    def test_competitor_and_human_first_are_abstain_even_without_ticket(self):
        """escalate=False (không tạo ticket) nhưng VẪN LÀ một lượt từ chối —
        phải tra theo escalate_reason, không theo escalate bool."""
        state, reason = _derive_runtime_state({"escalate_reason": "competitor_question", "escalate": False})
        assert (state, reason) == ("ABSTAIN", "missing_policy_evidence")

    def test_successful_hr_question_is_answer(self):
        state, reason = _derive_runtime_state({"intent": "hr_question", "response": "..."})
        assert (state, reason) == ("ANSWER", None)

    def test_greeting_and_clarify_are_answer(self):
        assert _derive_runtime_state({"intent": "greeting"}) == ("ANSWER", None)
        assert _derive_runtime_state({"intent": "ambiguous", "needs_clarification": True}) == ("ANSWER", None)


class TestAgentAnswerStateField:
    def test_defaults_to_answer_when_not_specified(self):
        answer = AgentAnswer(response="ok", intent="hr_question")
        assert answer.state == "ANSWER"
        assert answer.reason_code is None

    def test_accepts_out_of_scope_with_null_reason_code(self):
        answer = AgentAnswer(response="...", intent="pure_statutory", state="OUT_OF_SCOPE")
        assert answer.reason_code is None

    def test_accepts_abstain_with_reason_code(self):
        answer = AgentAnswer(
            response="...", intent="out_of_scope_or_personal", state="ABSTAIN", reason_code="missing_policy_evidence"
        )
        assert answer.reason_code == "missing_policy_evidence"


class TestLifecycleFilteringAtIngestion:
    """Test E (superseded policy leakage) ở tầng ingestion — xem
    test_retrieval.py cho tầng query filter tương ứng."""

    def _row(self, **overrides) -> RegistryRow:
        base = dict(
            source_file="x.md",
            category="company_regulations",
            status="processed",
            processed_path="data/processed/x.md",
            source_type="synthetic",
            is_official_policy=True,
            authority="tenant_official_policy",
            provenance="synthetic_demo",
            tenant="nexatech",
        )
        base.update(overrides)
        return RegistryRow(**base)

    def test_active_frozen_enabled_doc_is_eligible(self):
        row = self._row(publication_status="active", artifact_state="frozen", retrieval_enabled=True)
        assert rag_eligible_rows([row]) == [row]

    def test_superseded_doc_is_excluded_even_if_synthetic(self):
        row = self._row(publication_status="superseded")
        assert rag_eligible_rows([row]) == []

    def test_retrieval_disabled_doc_is_excluded(self):
        row = self._row(retrieval_enabled=False)
        assert rag_eligible_rows([row]) == []

    def test_defaults_are_active_frozen_enabled(self):
        row = self._row()
        assert (row.publication_status, row.artifact_state, row.retrieval_enabled) == ("active", "frozen", True)

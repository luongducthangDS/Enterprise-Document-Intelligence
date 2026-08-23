from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.nodes.knowledge_lookup import (
    _extract_location_from_query,
    _extract_target_date_ymd,
    knowledge_lookup_node,
)


def test_missing_location_does_not_guess_a_city():
    assert _extract_location_from_query("What is the hotel allowance?") is None


def test_explicit_query_date_is_used():
    assert _extract_target_date_ymd("Effective on 15/09/2027") == 20270915
    assert _extract_target_date_ymd("Effective on 2027-09-15") == 20270915


@pytest.mark.asyncio
async def test_resolved_knowledge_returns_final_answer_and_citations():
    evidence = SimpleNamespace(
        evidence_id="e-1",
        source_file="policy.md",
        document_code="POL-1",
        document_title="Travel Policy",
        section_heading="Hotel",
        exact_quote="Maximum amount is 1,200,000 VND.",
    )
    resolution = MagicMock(
        resolved=True,
        subject="hotel_allowance",
        value_numeric=1200000,
        currency="VND",
        unit="VND/night",
        resolved_by_document="POL-1",
        resolved_by_authority="COMPANY_POLICY",
        is_modified=False,
        evidences=[evidence],
    )
    resolution.model_dump.return_value = {"resolved": True}
    session_context = MagicMock()
    session_context.__enter__.return_value = MagicMock()

    with (
        patch("src.agents.nodes.knowledge_lookup.get_session", return_value=session_context),
        patch("src.agents.nodes.knowledge_lookup.DeterministicPolicyResolver") as resolver_cls,
        patch(
            "src.agents.nodes.knowledge_lookup.verbalize_policy_resolution",
            return_value="The hotel limit is 1,200,000 VND.",
        ),
    ):
        resolver_cls.return_value.resolve_hotel_allowance.return_value = resolution
        result = await knowledge_lookup_node(
            {
                "query": "Cong tac phi khach san tai tphcm on 2027-09-15?",
                "tenant_id": "nexatech",
            }
        )

    assert result["skip_retrieval"] is True
    assert result["generated_answer"] == "The hotel limit is 1,200,000 VND."
    assert result["citations"][0]["source_file"] == "policy.md"

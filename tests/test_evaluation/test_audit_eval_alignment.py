import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "audit_eval_alignment.py"
SPEC = importlib.util.spec_from_file_location("audit_eval_alignment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_audit_detects_source_and_contract_mismatches():
    dataset = [
        {
            "id": "qa_1",
            "type": "in_scope",
            "source_file": "legacy.pdf",
            "expected_intent": "hr_question",
        }
    ]
    qrels = {"qa_1": {"canonical::0001": 2}}
    agent_report = {"results": [{"id": "qa_1", "intent": "pure_statutory"}]}

    report = MODULE.audit(dataset, qrels, agent_report)

    assert report["issues_by_kind"] == {
        "declared_source_disagrees_with_qrels": 1,
        "intent_mismatch": 1,
    }


def test_audit_accepts_evidence_chunk_fallback():
    dataset = [{"id": "qa_1", "type": "in_scope", "evidence_chunk_id": "policy::0001"}]
    report = MODULE.audit(dataset, {})
    assert report["issue_count"] == 0

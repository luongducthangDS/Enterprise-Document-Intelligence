import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "finalize_nexatech_v2_qrels.py"
SPEC = importlib.util.spec_from_file_location("finalize_nexatech_v2_qrels", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_finalize_requires_complete_human_labels_and_answer_chunk():
    report = {
        "results": [
            {
                "id": "q1",
                "contract_flags": [],
                "candidates": [
                    {"chunk_id": "a", "human_relevance": 2},
                    {"chunk_id": "b", "human_relevance": 0},
                ],
            },
            {
                "id": "q2",
                "contract_flags": [],
                "candidates": [{"chunk_id": "c", "human_relevance": None}],
            },
        ]
    }

    qrels, issues = MODULE.validate_and_build(report)

    assert qrels == {"q1": {"a": 2}}
    assert {issue["kind"] for issue in issues} == {"missing_human_labels", "no_answer_chunk"}


def test_finalize_blocks_unresolved_contract_flag():
    report = {
        "results": [
            {
                "id": "q1",
                "contract_flags": ["scope_conflict"],
                "candidates": [{"chunk_id": "a", "human_relevance": 2}],
            }
        ]
    }

    qrels, issues = MODULE.validate_and_build(report)

    assert qrels == {"q1": {"a": 2}}
    assert issues == [{"id": "q1", "kind": "unresolved_contract_flags", "flags": ["scope_conflict"]}]

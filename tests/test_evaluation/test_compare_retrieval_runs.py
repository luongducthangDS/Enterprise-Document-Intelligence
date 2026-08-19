import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "compare_retrieval_runs.py"
SPEC = importlib.util.spec_from_file_location("compare_retrieval_runs", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _result(item_id: str, hit_rank: int, recall: float) -> dict:
    return {
        "id": item_id,
        "num_relevant": 1,
        "hit_rank": hit_rank,
        "recall_at_k": {"recall@5": recall},
    }


def test_compare_reports_paired_gains_and_losses():
    before = {"results": [_result("q1", 0, 0.0), _result("q2", 1, 1.0)]}
    after = {"results": [_result("q1", 2, 1.0), _result("q2", 0, 0.0)]}

    result = MODULE.compare(before, after)

    assert result["paired_queries"] == 2
    assert result["fixed_queries"] == ["q1"]
    assert result["broken_queries"] == ["q2"]
    assert result["hit_rate_test"]["diff"] == 0.0
    assert result["identical_per_query"] is False

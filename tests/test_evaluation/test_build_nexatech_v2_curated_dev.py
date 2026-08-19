import copy
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "build_nexatech_v2_curated_dev.py"
SPEC = importlib.util.spec_from_file_location("build_nexatech_v2_curated_dev", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _minimal_pool():
    results = []
    for query_id, decision in MODULE.CURATED.items():
        candidates = []
        for chunk_id in decision["labels"]:
            candidates.append({"chunk_id": chunk_id, "source_file": f"{chunk_id.split('::')[0]}.md"})
        results.append(
            {
                "id": query_id,
                "query": f"question {query_id}",
                "contextual_query": f"context {query_id}",
                "expected_source_file": "expected.md",
                "expected_states": ["ANSWER"],
                "contract_flags": [],
                "candidates": candidates,
            }
        )
    for query_id in MODULE.EXCLUDED:
        results.append(
            {
                "id": query_id,
                "query": f"question {query_id}",
                "contextual_query": f"context {query_id}",
                "expected_source_file": "expected.md",
                "expected_states": ["ANSWER"],
                "contract_flags": [],
                "candidates": [],
            }
        )
    return {"results": results}


def test_build_outputs_covers_every_query_and_keeps_release_boundary():
    dataset, qrels, report = MODULE.build_outputs(_minimal_pool())

    assert len(dataset) == len(MODULE.CURATED) == 27
    assert len(qrels) == len(dataset)
    assert report["excluded_query_count"] == len(MODULE.EXCLUDED) == 18
    assert report["release_ground_truth"] is False
    assert all(any(score == 2 for score in labels.values()) for labels in qrels.values())
    assert all(item["qrel_status"] == "curated_dev_single_reviewer" for item in dataset)
    assert all("question" not in item for item in dataset)
    assert all(item["query"].startswith("context ") for item in dataset)


def test_build_outputs_rejects_review_coverage_gap():
    pool = _minimal_pool()
    pool["results"].append(
        {
            "id": "not_reviewed",
            "query": "new",
            "contextual_query": "new",
            "expected_source_file": "x.md",
            "expected_states": ["ANSWER"],
            "contract_flags": [],
            "candidates": [],
        }
    )

    with pytest.raises(ValueError, match="Review coverage mismatch"):
        MODULE.build_outputs(pool)


def test_build_outputs_rejects_label_outside_candidate_pool():
    pool = copy.deepcopy(_minimal_pool())
    first_id = next(iter(MODULE.CURATED))
    target = next(item for item in pool["results"] if item["id"] == first_id)
    target["candidates"] = []

    with pytest.raises(ValueError, match="outside its candidate pool"):
        MODULE.build_outputs(pool)

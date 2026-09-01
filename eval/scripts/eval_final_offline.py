#!/usr/bin/env python3
"""Build the reproducible, network-free evaluation artifact for final submission."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.scripts.eval_boundary import evaluate as evaluate_boundary  # noqa: E402
from eval.scripts.eval_enterprise_suite import (  # noqa: E402
    run_acl_security_eval,
    run_hitl_extraction_eval,
    run_operations_qa_eval,
)


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    rate = successes / total
    denominator = 1 + z * z / total
    centre = rate + z * z / (2 * total)
    margin = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total))
    return [round((centre - margin) / denominator, 4), round((centre + margin) / denominator, 4)]


def product_qrel_alignment() -> dict:
    qrels_path = ROOT / "eval/datasets/product_retrieval_qrels.json"
    chunks_dir = ROOT / "data/product/chunks"
    qrels = json.loads(qrels_path.read_text(encoding="utf-8"))
    expected_ids = {chunk_id for labels in qrels.values() for chunk_id in labels}
    available_ids: set[str] = set()
    for path in chunks_dir.glob("*.json") if chunks_dir.exists() else []:
        for item in json.loads(path.read_text(encoding="utf-8")):
            available_ids.add(item["metadata"]["chunk_id"])
    present = expected_ids & available_ids
    missing = expected_ids - available_ids
    return {
        "gate": "product_retrieval_qrel_alignment",
        "status": "PASS" if not missing else "FAIL",
        "qrel_chunk_ids": len(expected_ids),
        "available_qrel_chunk_ids": len(present),
        "coverage": round(len(present) / len(expected_ids), 4) if expected_ids else None,
        "missing_qrel_chunk_ids": sorted(missing),
        "note": "A retrieval quality score is invalid while this alignment gate fails.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/results/final_offline_eval_20260901.json")
    parser.add_argument("--baseline", default="87a85aa34cc23e41cd2c6d8a1eb4331e31a79300")
    args = parser.parse_args()

    boundary_data = json.loads((ROOT / "eval/datasets/boundary_eval_set.json").read_text(encoding="utf-8"))
    boundary = evaluate_boundary(boundary_data)
    acl = run_acl_security_eval()
    hitl = run_hitl_extraction_eval()
    operations = run_operations_qa_eval()

    current_metrics = [
        {
            "id": "boundary_scenario_accuracy",
            "label": "Boundary scenario regression accuracy",
            "correct": boundary["counts"]["scenario"]["correct"],
            "total": boundary["counts"]["scenario"]["total"],
            "value": boundary["metrics"]["scenario"],
            "ci95_wilson": wilson_interval(
                boundary["counts"]["scenario"]["correct"], boundary["counts"]["scenario"]["total"]
            ),
            "interpretation": "Deterministic regression benchmark; not a production-accuracy estimate.",
        },
        {
            "id": "acl_fail_closed_rate",
            "label": "Cross-department ACL fail-closed rate",
            "correct": acl["passed"],
            "total": acl["total"],
            "value": round(acl["passed"] / acl["total"], 4) if acl["total"] else None,
            "ci95_wilson": wilson_interval(acl["passed"], acl["total"]),
            "interpretation": "Deterministic authorization cases, not a penetration test.",
        },
        {
            "id": "hitl_fixture_schema_completeness",
            "label": "HITL fixture schema completeness",
            "correct": hitl["valid"],
            "total": hitl["total"],
            "value": round(hitl["valid"] / hitl["total"], 4) if hitl["total"] else None,
            "ci95_wilson": wilson_interval(hitl["valid"], hitl["total"]),
            "interpretation": "Checks expected-data completeness only; it does not measure model extraction accuracy.",
        },
        {
            "id": "operations_fixture_completeness",
            "label": "Operations QA fixture completeness",
            "correct": operations["valid"],
            "total": operations["total"],
            "value": round(operations["valid"] / operations["total"], 4) if operations["total"] else None,
            "ci95_wilson": wilson_interval(operations["valid"], operations["total"]),
            "interpretation": "Checks question/answer/context/source fields only; it is not agent answer accuracy.",
        },
    ]

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_commit": args.baseline,
        "mode": "offline_reproducible",
        "network_calls": 0,
        "current_metrics": current_metrics,
        "invariant_violations": boundary["invariant_violations"],
        "product_retrieval_alignment": product_qrel_alignment(),
        "not_run": [
            {
                "evaluation": "router_dev",
                "reason": "Requires sending 68 evaluation questions to an external model API; not authorized in this run.",
            },
            {
                "evaluation": "live_retrieval_and_agent_e2e",
                "reason": "Requires aligned live Chroma collections and model-provider access.",
            },
        ],
    }

    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

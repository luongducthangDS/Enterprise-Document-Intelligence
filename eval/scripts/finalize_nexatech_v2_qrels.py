#!/usr/bin/env python3
"""Validate human candidate labels and finalize NexaTech v2 qrels."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def validate_and_build(report: dict) -> tuple[dict[str, dict[str, int]], list[dict]]:
    qrels: dict[str, dict[str, int]] = {}
    issues: list[dict] = []
    for result in report.get("results", []):
        result_id = result.get("id")
        flags = result.get("contract_flags") or []
        if flags and not result.get("contract_resolution"):
            issues.append({"id": result_id, "kind": "unresolved_contract_flags", "flags": flags})

        labels: dict[str, int] = {}
        missing_labels = []
        for candidate in result.get("candidates", []):
            score = candidate.get("human_relevance")
            if score not in (0, 1, 2):
                missing_labels.append(candidate.get("chunk_id"))
                continue
            if score > 0:
                labels[candidate["chunk_id"]] = int(score)
        if missing_labels:
            issues.append(
                {
                    "id": result_id,
                    "kind": "missing_human_labels",
                    "count": len(missing_labels),
                    "chunk_ids": missing_labels,
                }
            )
        if not any(score == 2 for score in labels.values()):
            issues.append({"id": result_id, "kind": "no_answer_chunk"})
        if not missing_labels and any(score == 2 for score in labels.values()):
            qrels[result_id] = dict(sorted(labels.items()))
    return qrels, issues


def _write_json(path: str, data: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="eval/results/nexatech_post_mvp_v2_candidate_pool.json")
    parser.add_argument("--out", default="eval/datasets/nexatech_post_mvp_v2_qrels.json")
    parser.add_argument("--issues-out", default="eval/results/nexatech_post_mvp_v2_adjudication_issues.json")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    with open(args.pool, encoding="utf-8") as handle:
        report = json.load(handle)
    qrels, issues = validate_and_build(report)
    issue_counts: dict[str, int] = {}
    for issue in issues:
        issue_counts[issue["kind"]] = issue_counts.get(issue["kind"], 0) + 1
    print(f"reviewed_queries={len(qrels)}/{report.get('query_count', 0)} issues={issue_counts}")
    if args.check_only:
        return 1 if issues else 0
    if issues:
        _write_json(args.issues_out, {"status": "INCOMPLETE", "counts": issue_counts, "issues": issues})
        print(f"not_finalized={args.issues_out}")
        return 1
    _write_json(args.out, qrels)
    print(f"saved={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

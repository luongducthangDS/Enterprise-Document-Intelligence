#!/usr/bin/env python3
"""Audit dataset/qrel/report alignment without calling models or vector stores."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.evaluation.retrieval_metrics import declared_source_stems, qrel_source_stems  # noqa: E402

SCOREABLE_TYPES = {"in_scope", "single_chunk", "multi_chunk"}


def audit(dataset: list[dict], qrels: dict, agent_report: dict | None = None, min_relevance: int = 2) -> dict:
    issues: list[dict] = []
    ids = [str(item.get("id") or "") for item in dataset]
    for item_id, count in Counter(ids).items():
        if not item_id:
            issues.append({"kind": "missing_id"})
        elif count > 1:
            issues.append({"kind": "duplicate_id", "id": item_id, "count": count})

    item_by_id = {str(item.get("id")): item for item in dataset if item.get("id")}
    for item_id, item in item_by_id.items():
        if item.get("retired") or item.get("type") not in SCOREABLE_TYPES:
            continue
        relevant = {
            chunk_id: score
            for chunk_id, score in (qrels.get(item_id) or {}).items()
            if int(score) >= min_relevance
        }
        if not relevant and item.get("evidence_chunk_id"):
            relevant = {item["evidence_chunk_id"]: 2}
        if not relevant:
            issues.append({"kind": "missing_qrel", "id": item_id})
            continue

        malformed = sorted(chunk_id for chunk_id in relevant if "::" not in chunk_id)
        if malformed:
            issues.append({"kind": "malformed_chunk_id", "id": item_id, "chunk_ids": malformed})

        declared = declared_source_stems(item)
        qrel_sources = qrel_source_stems(relevant)
        if declared and qrel_sources and declared.isdisjoint(qrel_sources):
            issues.append(
                {
                    "kind": "declared_source_disagrees_with_qrels",
                    "id": item_id,
                    "declared_sources": sorted(declared),
                    "qrel_sources": sorted(qrel_sources),
                }
            )

    if agent_report:
        for result in agent_report.get("results", []):
            item = item_by_id.get(str(result.get("id")))
            if not item or result.get("error"):
                continue
            expected_intent = item.get("expected_intent")
            observed_intent = result.get("intent")
            if expected_intent and observed_intent != expected_intent:
                issues.append(
                    {
                        "kind": "intent_mismatch",
                        "id": result.get("id"),
                        "expected": expected_intent,
                        "observed": observed_intent,
                    }
                )
            elif item.get("type") == "in_scope" and observed_intent == "pure_statutory":
                issues.append(
                    {
                        "kind": "legacy_scope_conflict",
                        "id": result.get("id"),
                        "dataset_type": "in_scope",
                        "observed_intent": "pure_statutory",
                    }
                )

    counts = Counter(issue["kind"] for issue in issues)
    return {
        "dataset_items": len(dataset),
        "qrel_queries": len(qrels),
        "issue_count": len(issues),
        "issues_by_kind": dict(sorted(counts.items())),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--qrels", default="")
    parser.add_argument("--agent-report", default="")
    parser.add_argument("--min-relevance", type=int, default=2, choices=[1, 2])
    parser.add_argument("--out", default="")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when alignment issues exist")
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as handle:
        dataset = json.load(handle)
    qrels = {}
    if args.qrels and os.path.exists(args.qrels):
        with open(args.qrels, encoding="utf-8") as handle:
            qrels = json.load(handle)
    agent_report = None
    if args.agent_report:
        with open(args.agent_report, encoding="utf-8") as handle:
            agent_report = json.load(handle)

    report = audit(dataset, qrels, agent_report, args.min_relevance)
    print(f"dataset_items={report['dataset_items']} qrel_queries={report['qrel_queries']}")
    print(f"alignment_issues={report['issue_count']}")
    for kind, count in report["issues_by_kind"].items():
        print(f"  {kind}: {count}")

    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved={output}")
    return 1 if args.strict and report["issue_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

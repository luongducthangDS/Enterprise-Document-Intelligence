#!/usr/bin/env python3
"""Paired comparison for two retrieval reports produced on the same queries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from _stats import paired_bootstrap  # noqa: E402


def compare(before_report: dict, after_report: dict, k: int = 5) -> dict:
    before = {item["id"]: item for item in before_report.get("results", [])}
    after = {item["id"]: item for item in after_report.get("results", [])}
    ids = sorted(
        item_id
        for item_id in before.keys() & after.keys()
        if before[item_id].get("num_relevant") and after[item_id].get("num_relevant")
    )

    hit_before = [float(bool(before[item_id].get("hit_rank") and before[item_id]["hit_rank"] <= k)) for item_id in ids]
    hit_after = [float(bool(after[item_id].get("hit_rank") and after[item_id]["hit_rank"] <= k)) for item_id in ids]
    recall_key = f"recall@{k}"
    recall_before = [float(before[item_id]["recall_at_k"][recall_key]) for item_id in ids]
    recall_after = [float(after[item_id]["recall_at_k"][recall_key]) for item_id in ids]

    fixed = [item_id for item_id, a, b in zip(ids, hit_before, hit_after) if not a and b]
    broken = [item_id for item_id, a, b in zip(ids, hit_before, hit_after) if a and not b]
    return {
        "k": k,
        "paired_queries": len(ids),
        "hit_rate_before": round(sum(hit_before) / len(ids), 4) if ids else 0.0,
        "hit_rate_after": round(sum(hit_after) / len(ids), 4) if ids else 0.0,
        "hit_rate_test": paired_bootstrap(hit_before, hit_after),
        "recall_before": round(sum(recall_before) / len(ids), 4) if ids else 0.0,
        "recall_after": round(sum(recall_after) / len(ids), 4) if ids else 0.0,
        "recall_test": paired_bootstrap(recall_before, recall_after),
        "fixed_queries": fixed,
        "broken_queries": broken,
        "identical_per_query": all(before[item_id].get("hit_rank") == after[item_id].get("hit_rank") for item_id in ids)
        and recall_before == recall_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    with open(args.before, encoding="utf-8") as handle:
        before_report = json.load(handle)
    with open(args.after, encoding="utf-8") as handle:
        after_report = json.load(handle)
    result = compare(before_report, after_report, args.k)

    print(f"paired_queries={result['paired_queries']} k={args.k}")
    print(
        f"Hit Rate@{args.k}: {result['hit_rate_before']:.1%} -> {result['hit_rate_after']:.1%} "
        f"(diff={result['hit_rate_test']['diff']:+.1%})"
    )
    print(
        f"Recall@{args.k}: {result['recall_before']:.1%} -> {result['recall_after']:.1%} "
        f"(diff={result['recall_test']['diff']:+.1%})"
    )
    print(f"fixed={result['fixed_queries']} broken={result['broken_queries']}")
    print(f"identical_per_query={result['identical_per_query']}")

    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved={output}")


if __name__ == "__main__":
    main()

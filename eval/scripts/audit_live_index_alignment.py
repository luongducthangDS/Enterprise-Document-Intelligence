#!/usr/bin/env python3
"""Audit qrels against the live Chroma collection without running queries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.retrieval import _collection  # noqa: E402
from src.evaluation.retrieval_metrics import live_index_alignment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--split", default="dev", choices=["dev", "heldout", "all"])
    parser.add_argument("--min-relevance", type=int, default=2, choices=[1, 2])
    parser.add_argument("--out", default="")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any scored qrel chunk is absent")
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as handle:
        dataset = json.load(handle)
    if args.split != "all":
        dataset = [item for item in dataset if item.get("split", "dev") == args.split]
    with open(args.qrels, encoding="utf-8") as handle:
        qrels = json.load(handle)

    snapshot = _collection().get(include=["metadatas"])
    report = live_index_alignment(
        dataset,
        qrels,
        set(snapshot.get("ids") or []),
        min_relevance=args.min_relevance,
    )
    report.update(
        {
            "dataset": args.dataset,
            "qrels": args.qrels,
            "split": args.split,
            "min_relevance": args.min_relevance,
        }
    )

    print(
        "benchmark_valid={benchmark_valid} qrel_chunks={available_qrel_chunk_labels}/"
        "{qrel_chunk_labels} ({qrel_chunk_label_coverage:.1%})".format(**report)
    )
    print(
        "queries_with_available_gold={queries_with_any_available_qrel}/"
        "{scored_queries} ({query_coverage:.1%})".format(**report)
    )
    print(
        f"index_sources={report['index_source_count']} qrel_sources={report['qrel_source_count']} "
        f"missing_qrel_sources={len(report['missing_qrel_sources'])}"
    )
    if report["unavailable_queries"]:
        print(f"unavailable_queries={report['unavailable_queries']}")

    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved={output}")
    return 1 if args.strict and not report["benchmark_valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

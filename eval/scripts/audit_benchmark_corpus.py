#!/usr/bin/env python3
"""Check that every source expected by a benchmark exists in live Chroma."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.retrieval import _collection  # noqa: E402
from src.evaluation.retrieval_metrics import normalize_source_stem  # noqa: E402


def audit(cases: list[dict], index_source_files: set[str]) -> dict:
    expected_counts = Counter(
        normalize_source_stem(case.get("source_file"))
        for case in cases
        if normalize_source_stem(case.get("source_file"))
    )
    available = {normalize_source_stem(source) for source in index_source_files if normalize_source_stem(source)}
    expected = set(expected_counts)
    missing = sorted(expected - available)
    return {
        "benchmark_case_count": len(cases),
        "benchmark_source_count": len(expected),
        "index_source_count": len(available),
        "covered_source_count": len(expected & available),
        "all_expected_sources_available": not missing,
        "missing_sources": missing,
        "extra_index_sources": sorted(available - expected),
        "cases_by_expected_source": dict(sorted(expected_counts.items())),
        "behavior_only_cases": sum(not case.get("source_file") for case in cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as handle:
        cases = json.load(handle)
    snapshot = _collection().get(include=["metadatas"])
    source_files = {
        metadata.get("source_file", "")
        for metadata in (snapshot.get("metadatas") or [])
        if metadata
    }
    report = audit(cases, source_files)
    print(
        f"benchmark_sources={report['covered_source_count']}/{report['benchmark_source_count']} "
        f"index_sources={report['index_source_count']} behavior_only_cases={report['behavior_only_cases']}"
    )
    if report["missing_sources"]:
        print(f"missing_sources={report['missing_sources']}")
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"saved={output}")
    return 1 if args.strict and report["missing_sources"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

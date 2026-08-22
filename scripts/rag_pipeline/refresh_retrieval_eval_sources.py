#!/usr/bin/env python3
"""Refresh benchmark source files and seed chunk IDs from current qrels/chunks."""

from __future__ import annotations

import glob
import json
import os


DATASET = "eval/datasets/retrieval_eval_set.json"
QRELS = "eval/datasets/retrieval_eval_qrels.json"


def main() -> None:
    metadata_by_id: dict[str, dict] = {}
    for path in glob.glob("data/chunks/*.json"):
        with open(path, encoding="utf-8") as handle:
            for chunk in json.load(handle):
                metadata_by_id[chunk["metadata"]["chunk_id"]] = chunk["metadata"]

    with open(DATASET, encoding="utf-8") as handle:
        items = json.load(handle)
    with open(QRELS, encoding="utf-8") as handle:
        qrels = json.load(handle)

    refreshed = 0
    for item in items:
        relevant = qrels.get(item["id"])
        if not relevant:
            continue
        chunk_ids = list(relevant)
        sources = sorted(
            {
                metadata_by_id[chunk_id]["source_file"]
                for chunk_id in chunk_ids
                if chunk_id in metadata_by_id
            }
        )
        item["seed_chunk_ids"] = chunk_ids
        item["source_files"] = sources
        item["num_relevant"] = len(chunk_ids)
        item["num_highly_relevant"] = sum(1 for score in relevant.values() if score >= 2)
        refreshed += 1

    temporary = f"{DATASET}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, DATASET)
    print(f"Refreshed {refreshed} active benchmark entries")


if __name__ == "__main__":
    main()
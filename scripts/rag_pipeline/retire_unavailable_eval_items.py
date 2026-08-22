#!/usr/bin/env python3
"""Mark eval questions whose evidence is absent from the active corpus as retired."""

from __future__ import annotations

import json
import os


PAIRS = (
    ("eval/datasets/retrieval_eval_set.json", "eval/datasets/retrieval_eval_qrels.json"),
    ("eval/datasets/qa_eval_set.json", "eval/datasets/retrieval_qrels.json"),
    ("eval/datasets/qa_heldout_set.json", "eval/datasets/retrieval_qrels.json"),
)


def write_json_atomic(path: str, value: object) -> None:
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def main() -> None:
    for dataset_path, qrels_path in PAIRS:
        if not os.path.exists(dataset_path):
            continue
        with open(dataset_path, encoding="utf-8") as handle:
            items = json.load(handle)
        with open(qrels_path, encoding="utf-8") as handle:
            qrels = json.load(handle)

        retired = active = 0
        for item in items:
            if item["id"] in qrels:
                item.pop("retired", None)
                item.pop("retired_reason", None)
                active += 1
            else:
                item["retired"] = True
                item["retired_reason"] = "source_not_in_active_corpus"
                retired += 1
        write_json_atomic(dataset_path, items)
        print(f"{dataset_path}: active={active}, retired={retired}")


if __name__ == "__main__":
    main()
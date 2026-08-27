#!/usr/bin/env python3
"""Fail-fast checks for Product ownership and retrieval eval alignment."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DEFAULT_REGISTRY = "data/metadata/product_document_registry.csv"
DEFAULT_SET = "eval/datasets/product_retrieval_eval_set.json"
DEFAULT_QRELS = "eval/datasets/product_retrieval_qrels.json"
DEFAULT_CHUNKS = "data/product/chunks"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--dataset", default=DEFAULT_SET)
    parser.add_argument("--qrels", default=DEFAULT_QRELS)
    parser.add_argument("--chunks-dir", default=DEFAULT_CHUNKS)
    args = parser.parse_args()

    errors: list[str] = []
    with Path(args.registry).open(encoding="utf-8", newline="") as handle:
        registry = list(csv.DictReader(handle))
    for row in registry:
        if row.get("department", "").strip().casefold() != "product":
            errors.append(f"{row.get('source_file')}: department != Product")
        if row.get("document_domain") != "COMPANY_POLICY":
            errors.append(f"{row.get('source_file')}: document_domain != COMPANY_POLICY")
        if row.get("access_scope") not in {"DEPARTMENT", "COMPANY_WIDE"}:
            errors.append(f"{row.get('source_file')}: unsupported access_scope")
        if not row.get("owner", "").strip():
            errors.append(f"{row.get('source_file')}: missing owner")

    chunks = {}
    for path in Path(args.chunks_dir).glob("*.json"):
        for item in json.loads(path.read_text(encoding="utf-8")):
            metadata = item["metadata"]
            chunks[metadata["chunk_id"]] = metadata
            if metadata.get("department") != "Product":
                errors.append(f"{metadata['chunk_id']}: department != Product")
            if metadata.get("document_domain") != "COMPANY_POLICY":
                errors.append(f"{metadata['chunk_id']}: document_domain != COMPANY_POLICY")
            if not metadata.get("owner"):
                errors.append(f"{metadata['chunk_id']}: missing owner")
            if metadata.get("effective_date_ymd") in (None, 1, 10101):
                errors.append(f"{metadata['chunk_id']}: invalid effective_date_ymd")

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    qrels = json.loads(Path(args.qrels).read_text(encoding="utf-8"))
    dataset_ids = {item["id"] for item in dataset}
    demo_cases = [item for item in dataset if item.get("demo_priority")]
    for item in dataset:
        if item.get("department") != "Product":
            errors.append(f"{item['id']}: department != Product")
        if not item.get("owner"):
            errors.append(f"{item['id']}: missing owner")
        if item["type"] == "in_scope" and not qrels.get(item["id"]):
            errors.append(f"{item['id']}: missing qrels")
    for item in demo_cases:
        if item.get("difficulty") != "hard":
            errors.append(f"{item['id']}: demo case must have difficulty=hard")
        if item.get("reasoning") != "multi_document_synthesis":
            errors.append(f"{item['id']}: demo case must require multi-document synthesis")
        if len(item.get("source_files", [])) < 3:
            errors.append(f"{item['id']}: demo case must declare at least 3 sources")
    demo_modalities = {modality for item in demo_cases for modality in item.get("modalities", [])}
    if len(demo_cases) < 3:
        errors.append("hard-demo coverage requires at least 3 cases")
    if not any("table" in modality for modality in demo_modalities):
        errors.append("hard-demo coverage missing table modality")
    if "xlsx_chart" not in demo_modalities:
        errors.append("hard-demo coverage missing xlsx_chart modality")
    if "scanned_image" not in demo_modalities:
        errors.append("hard-demo coverage missing scanned_image modality")
    for eval_id in qrels:
        if eval_id not in dataset_ids:
            errors.append(f"qrels references unknown eval id: {eval_id}")
        for chunk_id in qrels[eval_id]:
            if chunk_id not in chunks:
                errors.append(f"{eval_id}: stale qrel chunk {chunk_id}")

    if errors:
        print("Product dataset integrity: FAIL")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)
    print(f"Product dataset integrity: PASS ({len(registry)} registry rows, {len(chunks)} chunks, {len(dataset)} eval cases)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Backfill field `source_file` cho các câu in_scope trong
eval/datasets/qa_eval_set.json — xác định chính xác `ground_truth_context` của
mỗi câu nằm ở file processed nào (trong 1-2 file nguồn của category đó, xem
EVAL_EXCERPT_SOURCES ở scripts/collect_data.py), rồi map sang đúng giá trị
`source_file` như lưu trong metadata Chroma (basename gốc theo
data/metadata/document_registry.csv — có thể là .pdf/.docx, không nhất thiết
.md, vì đó là tên file RAW gốc trước khi extract).

Mục đích: có 1 nhãn "đúng document" tường minh cho retrieval eval, thay vì chỉ
suy luận gián tiếp qua so khớp chuỗi con ground_truth_context (dễ bị lệch khi
chunking cắt vỡ câu giữa 2 chunk — xem CLAUDE.md [2026-08-05]).

Chạy: python scripts/backfill_eval_source_file.py [--dry-run]
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from _text_utils import normalize_for_match  # noqa: E402
from collect_data import EVAL_EXCERPT_SOURCES  # noqa: E402

EVAL_SET_PATH = "eval/datasets/qa_eval_set.json"
REGISTRY_PATH = "data/metadata/document_registry.csv"


def _load_stem_to_source_file() -> dict[str, str]:
    """stem (tên file không đuôi) -> source_file THẬT như lưu trong Chroma metadata
    (basename file RAW gốc, có thể .pdf/.docx/.md)."""
    mapping = {}
    with open(REGISTRY_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stem = os.path.splitext(row["source_file"])[0]
            mapping[stem] = row["source_file"]
    return mapping


def _processed_path_for_raw(raw_path: str) -> str:
    stem = os.path.splitext(os.path.basename(raw_path))[0]
    return os.path.join("data", "processed", f"{stem}.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stem_to_source_file = _load_stem_to_source_file()

    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        items = json.load(f)

    matched, ambiguous, unmatched = 0, 0, 0
    for item in items:
        if item["type"] != "in_scope":
            continue
        needle = normalize_for_match(item["ground_truth_context"])
        candidates = EVAL_EXCERPT_SOURCES.get(item["category"], [])

        hits = []
        for raw_path in candidates:
            processed_path = _processed_path_for_raw(raw_path)
            if not os.path.exists(processed_path):
                continue
            with open(processed_path, encoding="utf-8") as f:
                content = normalize_for_match(f.read())
            if needle and needle in content:
                stem = os.path.splitext(os.path.basename(raw_path))[0]
                source_file = stem_to_source_file.get(stem)
                if source_file:
                    hits.append(source_file)

        unique_hits = sorted(set(hits))
        if len(unique_hits) == 1:
            item["source_file"] = unique_hits[0]
            matched += 1
        elif len(unique_hits) > 1:
            # trùng khớp ở cả 2 file nguồn của category (hiếm) -> để cảnh báo, không đoán
            print(f"[AMBIGUOUS] {item['id']}: khớp {len(unique_hits)} file -> {unique_hits}")
            ambiguous += 1
        else:
            print(f"[MISS] {item['id']}: không khớp file nào trong {candidates}")
            unmatched += 1

    print(f"\nĐã map: {matched}, mập mờ (>1 file): {ambiguous}, không map được: {unmatched}")

    if not args.dry_run:
        tmp_path = f"{EVAL_SET_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        with open(tmp_path, encoding="utf-8") as f:
            if len(json.load(f)) != len(items):
                raise RuntimeError("verify ghi file thất bại, huỷ replace")
        os.replace(tmp_path, EVAL_SET_PATH)
        print(f"Đã ghi {EVAL_SET_PATH}")


if __name__ == "__main__":
    main()

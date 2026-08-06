#!/usr/bin/env python3
"""Sửa các câu `ground_truth_context` trong eval/datasets/qa_eval_set.json KHÔNG
tồn tại nguyên văn trong data/processed/ (GLM-5.2 âm thầm paraphrase khi sinh eval
set dù prompt đã yêu cầu "trích NGUYÊN VĂN" — xem CLAUDE.md [2026-08-05]).

Cách sửa: KHÔNG dùng LLM lại (đó chính là nguồn gây lỗi ban đầu) — dùng
difflib.SequenceMatcher để tìm đoạn/câu THẬT trong đúng file nguồn của category
đó, khớp gần nhất với `expected_answer` + `ground_truth_context` cũ. Kết quả luôn
là text cắt nguyên từ nguồn thật -> đảm bảo verbatim 100%.

Chỉ ghi đè khi similarity ratio >= --min-ratio (mặc định 0.3); câu nào không đạt
được để nguyên + liệt kê "cần xem tay" cuối báo cáo, không đoán bừa.

Chạy: python scripts/fix_eval_ground_truth.py [--min-ratio 0.3] [--dry-run]
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
_eval_scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "scripts")
sys.path.insert(0, _scripts_dir)
sys.path.insert(0, _eval_scripts_dir)
sys.stdout.reconfigure(encoding="utf-8")

from _text_utils import normalize_for_match as _normalize  # noqa: E402
from collect_data import EVAL_EXCERPT_SOURCES  # noqa: E402

EVAL_SET_PATH = "eval/datasets/qa_eval_set.json"


def _is_verbatim(context: str, corpus_texts: list[str]) -> bool:
    needle = _normalize(context)
    return any(needle in _normalize(c) for c in corpus_texts)


def _processed_path_for_raw(raw_path: str) -> str:
    stem = os.path.splitext(os.path.basename(raw_path))[0]
    return os.path.join("data", "processed", f"{stem}.md")


def _split_candidates(text: str) -> list[str]:
    """Tách văn bản thành các đoạn (theo dòng trống) + câu (theo dấu câu/newline),
    để có candidate ở cả 2 độ dài khi tìm khớp gần nhất."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentences: list[str] = []
    for p in paragraphs:
        for s in re.split(r"(?<=[.!?])\s+|\n", p):
            s = s.strip(" -*#")
            if len(s) >= 15:
                sentences.append(s)
    # đoạn dài trước (ưu tiên context có ngữ cảnh đầy đủ hơn khi ratio ngang nhau)
    return paragraphs + sentences


def _best_match(reference: str, corpus_texts: list[str]) -> tuple[str, float]:
    best_text, best_ratio = "", 0.0
    for corpus in corpus_texts:
        for candidate in _split_candidates(corpus):
            ratio = difflib.SequenceMatcher(None, reference, candidate).ratio()
            if ratio > best_ratio:
                best_text, best_ratio = candidate, ratio
    return best_text, best_ratio


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-ratio", type=float, default=0.3, help="Ngưỡng similarity tối thiểu để chấp nhận sửa")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in ra, không ghi file")
    args = parser.parse_args()

    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        items = json.load(f)

    # cache nội dung processed theo category
    category_corpus: dict[str, list[str]] = {}
    for category, raw_paths in EVAL_EXCERPT_SOURCES.items():
        texts = []
        for raw_path in raw_paths:
            processed_path = _processed_path_for_raw(raw_path)
            if os.path.exists(processed_path):
                with open(processed_path, encoding="utf-8") as f:
                    texts.append(f.read())
        category_corpus[category] = texts

    fixed, need_review, already_ok = [], [], 0
    for item in items:
        if item["type"] != "in_scope":
            continue
        corpus_texts = category_corpus.get(item["category"], [])
        if _is_verbatim(item["ground_truth_context"], corpus_texts):
            already_ok += 1
            continue

        reference = f"{item.get('ground_truth_context', '')} {item.get('expected_answer', '')}".strip()
        best_text, ratio = _best_match(reference, corpus_texts)

        if ratio >= args.min_ratio and best_text:
            print(f"[FIX] {item['id']} (ratio={ratio:.2f})")
            print(f"      cũ: {item['ground_truth_context'][:100]!r}")
            print(f"      mới: {best_text[:100]!r}")
            if not args.dry_run:
                item["ground_truth_context"] = best_text
            fixed.append(item["id"])
        else:
            need_review.append((item["id"], ratio))

    print(f"\n=== Tổng kết ===\nĐã đúng sẵn: {already_ok}\nĐã sửa: {len(fixed)} -> {fixed}")
    if need_review:
        print(f"Cần xem tay (ratio < {args.min_ratio}, không tự sửa): {len(need_review)}")
        for id_, ratio in need_review:
            print(f"  - {id_} (best ratio={ratio:.2f})")

    if not args.dry_run and fixed:
        tmp_path = f"{EVAL_SET_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        with open(tmp_path, encoding="utf-8") as f:
            if len(json.load(f)) != len(items):
                raise RuntimeError("verify ghi file thất bại, huỷ replace")
        os.replace(tmp_path, EVAL_SET_PATH)
        print(f"\nĐã ghi {EVAL_SET_PATH}")


if __name__ == "__main__":
    main()

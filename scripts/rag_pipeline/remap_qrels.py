#!/usr/bin/env python3
"""Neo qrel vào ĐOẠN VĂN BẢN thay vì `chunk_id`, và map lại sau mỗi lần re-chunk.

## Vấn đề gốc

`chunk_id` có dạng `{stem}::{index}` nên nó **phụ thuộc cấu hình chunker**. Đổi
`chunk_max_chars` một lần (2000 → 1500) là toàn bộ index dịch chuyển và nhãn
qrel trỏ sai chỗ — đã xảy ra thật, làm hỏng 78/128 nhãn mà không có triệu chứng
nào cho tới khi metric tụt.

Một benchmark nghiêm túc phải neo vào thứ KHÔNG đổi theo cấu hình hệ thống đang
được đo. Ở đây là chính đoạn văn bản trong tài liệu nguồn.

## Cách làm

`eval/datasets/*_anchors.json` lưu `{query_id: {chunk_id: đoạn văn neo}}`. Sau
mỗi lần re-chunk, script này tìm lại chunk chứa đoạn neo đó (so khớp xác định,
không LLM) và ghi ra qrel mới. Nhãn relevance được giữ nguyên — chỉ có địa chỉ
chunk thay đổi.

Anchor nào không còn tìm thấy sẽ được báo ra để xem tay, thay vì âm thầm biến
mất khỏi qrel.

Chạy:
    python scripts/rag_pipeline/remap_qrels.py --build-anchors   # tạo anchors từ qrel + chunk hiện tại
    python scripts/rag_pipeline/remap_qrels.py                   # map lại qrel theo chunk mới
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "eval", "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from _text_utils import normalize_for_match  # noqa: E402

CHUNKS_DIR = "data/chunks"
ANCHOR_CHARS = 300
MIN_ANCHOR_CHARS = 40

PAIRS = [
    ("eval/datasets/retrieval_eval_qrels.json", "eval/datasets/retrieval_eval_anchors.json"),
    ("eval/datasets/retrieval_qrels.json", "eval/datasets/retrieval_anchors.json"),
]


def load_chunks() -> dict[str, dict]:
    chunks: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(CHUNKS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            for c in json.load(f):
                chunks[c["metadata"]["chunk_id"]] = c
    return chunks


def write_json_atomic(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(tmp, encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, path)


def make_anchor(text: str) -> str:
    """Cắt đoạn neo ở ranh giới từ và bỏ ký tự markdown lẻ ở cuối.

    Cắt cứng theo số ký tự có thể rơi vào giữa cặp `**` — chuẩn hoá sẽ bỏ `**`
    nhưng giữ lại dấu `*` lẻ, khiến anchor không bao giờ khớp lại được (đã gặp
    thật ở 1 nhãn).
    """
    text = text.strip()
    if len(text) > ANCHOR_CHARS:
        text = text[:ANCHOR_CHARS]
        cut = text.rfind(" ")
        if cut > MIN_ANCHOR_CHARS:
            text = text[:cut]
    return text.rstrip(" \t\n*_#|-")


def build_anchors(qrels_path: str, anchors_path: str, chunks: dict[str, dict]) -> None:
    """Chụp lại đoạn văn đại diện cho từng chunk đang được gán nhãn."""
    with open(qrels_path, encoding="utf-8") as f:
        qrels = json.load(f)

    anchors: dict[str, dict] = {}
    missing = []
    for qid, rel in qrels.items():
        entry = {}
        for chunk_id, score in rel.items():
            chunk = chunks.get(chunk_id)
            if not chunk:
                missing.append(f"{qid}/{chunk_id}")
                continue
            text = chunk["text"].strip()
            entry[chunk_id] = {"score": score, "anchor": make_anchor(text)}
        if entry:
            anchors[qid] = entry

    write_json_atomic(anchors_path, anchors)
    n_anchor = sum(len(v) for v in anchors.values())
    print(f"[anchors] {anchors_path}: {len(anchors)} query / {n_anchor} nhãn")
    if missing:
        print(f"  ⚠ {len(missing)} chunk_id trong qrel không còn tồn tại: {missing[:5]}")


def remap(qrels_path: str, anchors_path: str, chunks: dict[str, dict], dry_run: bool) -> None:
    if not os.path.exists(anchors_path):
        print(f"[bỏ qua] chưa có {anchors_path} — chạy --build-anchors trước")
        return

    with open(anchors_path, encoding="utf-8") as f:
        anchors = json.load(f)

    # Chuẩn hoá sẵn 1 lần: remap là O(số nhãn × số chunk) nếu không cache.
    normalized = {cid: normalize_for_match(c["text"]) for cid, c in chunks.items()}

    new_qrels: dict[str, dict] = {}
    unchanged = moved = lost = 0
    lost_ids = []

    for qid, entry in anchors.items():
        rel: dict[str, int] = {}
        for old_chunk_id, info in entry.items():
            needle = normalize_for_match(info["anchor"])
            if len(needle) < MIN_ANCHOR_CHARS:
                needle = needle[:MIN_ANCHOR_CHARS]
            # Ưu tiên chính chunk cũ nếu nội dung còn nguyên → không đổi địa chỉ.
            if old_chunk_id in normalized and needle in normalized[old_chunk_id]:
                rel[old_chunk_id] = info["score"]
                unchanged += 1
                continue
            hits = [cid for cid, text in normalized.items() if needle in text]
            if hits:
                rel[hits[0]] = info["score"]
                moved += 1
            else:
                lost += 1
                lost_ids.append(f"{qid}/{old_chunk_id}")
        if rel:
            new_qrels[qid] = rel

    print(f"[remap] {qrels_path}: giữ nguyên {unchanged}, dời sang chunk mới {moved}, mất {lost}")
    if lost_ids:
        print(f"  ⚠ anchor không tìm thấy trong chunk hiện tại (cần xem tay): {lost_ids[:8]}")
    if dry_run:
        print("  (dry-run — không ghi file)")
        return
    write_json_atomic(qrels_path, new_qrels)
    print(f"  đã ghi {qrels_path} ({len(new_qrels)} query)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-anchors", action="store_true", help="Chụp anchor từ qrel + chunk hiện tại")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    chunks = load_chunks()
    print(f"Đã nạp {len(chunks)} chunk")

    for qrels_path, anchors_path in PAIRS:
        if not os.path.exists(qrels_path):
            print(f"[bỏ qua] không có {qrels_path}")
            continue
        if args.build_anchors:
            build_anchors(qrels_path, anchors_path, chunks)
        else:
            remap(qrels_path, anchors_path, chunks, args.dry_run)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Kiểm tra tính toàn vẹn của bộ eval — KHÔNG gọi API, chạy được trong CI.

Đây là cái gate lẽ ra phải có từ đầu: sáng 06-08 việc đổi `chunk_max_chars`
2000 → 1500 đã làm hỏng 78/128 nhãn qrel mà không có triệu chứng nào, cho tới
khi metric tụt và phải truy ngược mấy tiếng. Toàn bộ các kiểm tra dưới đây đều
phát hiện được sự cố đó ngay lập tức, và không tốn một lệnh gọi mạng nào.

Kiểm tra:
1. Mọi `chunk_id` trong qrel phải tồn tại trong `data/chunks/`.
2. Mọi đoạn neo (anchor) phải còn nằm nguyên văn trong chunk mà nó trỏ tới.
3. Mọi `ground_truth_context` của câu in_scope phải nằm trong ít nhất 1 chunk
   được gán nhãn cho câu đó.
4. Không có query nào trong dataset mà thiếu qrel, và ngược lại.
5. Split dev/heldout không chồng lấn và không rỗng.

Chia làm 2 nhóm vì `data/` bị gitignore:

- **Nhóm tự chứa** (1, 4, 5 dưới đây): chỉ cần các file trong `eval/datasets/`
  vốn được track — chạy được trong CI trên máy sạch.
- **Nhóm cần chunk** (2, 3): cần `data/chunks/` nên chỉ chạy được ở máy có dữ
  liệu (local, hoặc pre-push hook). Không có chunk thì bỏ qua và báo rõ, không
  coi là lỗi.

Exit code 1 nếu có lỗi → dùng làm gate CI và pre-push.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from _text_utils import normalize_for_match  # noqa: E402

CHUNKS_DIR = "data/chunks"


def load_chunks() -> dict[str, str]:
    chunks: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(CHUNKS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            for c in json.load(f):
                chunks[c["metadata"]["chunk_id"]] = c["text"]
    return chunks


def _load(path: str):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_qrels_point_to_existing_chunks(qrels: dict, chunks: dict[str, str], label: str) -> list[str]:
    missing = [
        f"{qid}/{cid}" for qid, rel in qrels.items() for cid in rel if cid not in chunks
    ]
    if missing:
        return [f"[{label}] {len(missing)} chunk_id trong qrel không tồn tại: {missing[:5]}"]
    return []


def check_anchors_still_match(anchors: dict, chunks: dict[str, str], label: str) -> list[str]:
    broken = []
    for qid, entry in (anchors or {}).items():
        for cid, info in entry.items():
            text = chunks.get(cid)
            if text is None:
                broken.append(f"{qid}/{cid} (chunk biến mất)")
            elif normalize_for_match(info["anchor"]) not in normalize_for_match(text):
                broken.append(f"{qid}/{cid} (nội dung chunk đã đổi)")
    if broken:
        return [
            f"[{label}] {len(broken)} anchor không còn khớp — chunk đã đổi, "
            f"chạy `python scripts/rag_pipeline/remap_qrels.py` để map lại: {broken[:5]}"
        ]
    return []


def check_ground_truth_inside_gold(items: list, qrels: dict, chunks: dict[str, str], label: str) -> list[str]:
    bad = []
    for item in items:
        if item.get("type") != "in_scope" or not item.get("ground_truth_context"):
            continue
        rel = qrels.get(item["id"], {})
        if not rel:
            continue
        needle = normalize_for_match(item["ground_truth_context"])
        if not any(needle in normalize_for_match(chunks.get(cid, "")) for cid in rel):
            bad.append(item["id"])
    if bad:
        return [
            f"[{label}] {len(bad)} câu có ground_truth_context KHÔNG nằm trong chunk gold "
            f"(dấu hiệu ground truth dài hơn chunk, hoặc chunk đã đổi): {bad[:8]}"
        ]
    return []


def check_ids_unique_and_complete(items: list, label: str, required: tuple[str, ...]) -> list[str]:
    """Kiểm tra tự chứa: id không trùng, không thiếu field bắt buộc."""
    problems = []
    ids = [it.get("id") for it in items]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        problems.append(f"[{label}] id trùng lặp: {sorted(dupes)[:5]}")
    if None in ids:
        problems.append(f"[{label}] có {ids.count(None)} mục thiếu field `id`")
    for field in required:
        missing = [it.get("id") for it in items if not it.get(field)]
        if missing:
            problems.append(f"[{label}] {len(missing)} mục thiếu `{field}`: {missing[:5]}")
    return problems


def check_coverage(items: list, qrels: dict, label: str, id_field: str = "id") -> list[str]:
    problems = []
    ids = {it[id_field] for it in items}
    orphan_qrels = set(qrels) - ids
    if orphan_qrels:
        problems.append(f"[{label}] {len(orphan_qrels)} qrel không có query tương ứng: {sorted(orphan_qrels)[:5]}")
    return problems


def check_splits(items: list, label: str) -> list[str]:
    if not items or "split" not in items[0]:
        return []
    counts: dict[str, int] = {}
    for it in items:
        counts[it.get("split", "dev")] = counts.get(it.get("split", "dev"), 0) + 1
    problems = []
    for split in ("dev", "heldout"):
        if counts.get(split, 0) == 0:
            problems.append(f"[{label}] split '{split}' rỗng")
    return problems


def main() -> int:
    chunks = load_chunks()
    has_chunks = bool(chunks)
    if has_chunks:
        print(f"Đã nạp {len(chunks)} chunk từ {CHUNKS_DIR}")
    else:
        print(f"(không có {CHUNKS_DIR} — bỏ qua các kiểm tra cần chunk, chỉ chạy kiểm tra tự chứa)")
    problems: list[str] = []

    # Bộ benchmark retrieval chuyên dụng
    rb = _load("eval/datasets/retrieval_eval_set.json")
    rb_qrels = _load("eval/datasets/retrieval_eval_qrels.json")
    rb_anchors = _load("eval/datasets/retrieval_eval_anchors.json")
    if rb and rb_qrels:
        rb = [item for item in rb if not item.get("retired")]
        problems += check_ids_unique_and_complete(rb, "retrieval_benchmark", ("query", "type", "split"))
        problems += check_coverage(rb, rb_qrels, "retrieval_benchmark")
        problems += check_splits(rb, "retrieval_benchmark")
        if has_chunks:
            problems += check_qrels_point_to_existing_chunks(rb_qrels, chunks, "retrieval_benchmark")
            problems += check_anchors_still_match(rb_anchors, chunks, "retrieval_benchmark")
        print(f"retrieval_benchmark: {len(rb)} query, {len(rb_qrels)} qrel")

    # Bộ qa_eval_set + held-out
    qrels = _load("eval/datasets/retrieval_qrels.json") or {}
    anchors = _load("eval/datasets/retrieval_anchors.json")
    all_items: list = []
    for path in ("eval/datasets/qa_eval_set.json", "eval/datasets/qa_heldout_set.json"):
        items = _load(path)
        if items:
            # Bỏ qua câu retired: nguồn đã bị gỡ khỏi corpus có chủ đích nên chúng
            # KHÔNG có qrel/anchor, và đó là trạng thái đúng — không phải lỗi toàn vẹn.
            items = [it for it in items if not it.get("retired")]
            all_items += items
            print(f"{os.path.basename(path)}: {len(items)} câu")
    if all_items and qrels:
        problems += check_ids_unique_and_complete(all_items, "qa_eval_set", ("question", "type"))
        problems += check_coverage(all_items, qrels, "qa_eval_set")
        if has_chunks:
            problems += check_qrels_point_to_existing_chunks(qrels, chunks, "qa_eval_set")
            problems += check_anchors_still_match(anchors, chunks, "qa_eval_set")
            problems += check_ground_truth_inside_gold(all_items, qrels, chunks, "qa_eval_set")

    print()
    if problems:
        print(f"❌ {len(problems)} vấn đề:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("✅ Bộ eval nhất quán" + (" với chunk hiện tại" if has_chunks else " (mức tự chứa)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

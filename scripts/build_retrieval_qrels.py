#!/usr/bin/env python3
"""Xây `eval/datasets/retrieval_qrels.json` (qrel chunk-level cho retrieval eval)
+ backfill field `relevant_chunk_ids` vào `qa_eval_set.json` cho 60 câu in_scope.

Cách làm — KHÔNG dùng LLM (bài học từ vụ ground_truth_context bị paraphrase dù
yêu cầu verbatim, xem CLAUDE.md [2026-08-05]): tìm chunk_id chứa `ground_truth_context`
(đã verify verbatim 100%) một cách xác định (deterministic string match), lấy dữ
liệu TRỰC TIẾP TỪ Chroma Cloud (`collection.get(where={"source_file": ...})`)
thay vì file `data/chunks/*.json` cục bộ — vì local file từng ghi nhận bị lệch so
với chunker mới nhất cho 1 số tài liệu (xem CLAUDE.md), trong khi Chroma Cloud là
nguồn thật đang được agent retrieve, tránh sai lệch chunk_id.

Relevance score: 2 = chunk chứa `ground_truth_context` (verbatim, chắc chắn liên
quan). Chưa tự động gán multi-chunk (relevance=1, "supporting") — theo đúng
khuyến nghị risk-mitigation trong plan_eval.md: bắt đầu single-chunk qrel trước,
review tay các câu multi-chunk sau thay vì đoán bằng LLM.

Chạy: python scripts/build_retrieval_qrels.py [--dry-run]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from _text_utils import normalize_for_match  # noqa: E402
from src.agents.nodes.retrieval import _collection  # noqa: E402
from src.config import get_settings  # noqa: E402

EVAL_SET_PATH = "eval/datasets/qa_eval_set.json"
QRELS_PATH = "eval/datasets/retrieval_qrels.json"

_source_file_cache: dict[str, list[dict]] = {}


def _chunks_for_source_file(source_file: str) -> list[dict]:
    # source_file might have .md or .pdf. We use stem to query Chroma.
    stem = os.path.splitext(os.path.basename(source_file))[0]
    if stem not in _source_file_cache:
        collection = _collection()
        result = collection.get(where={"source_stem": stem}, include=["documents", "metadatas"])
        chunks = [
            {"chunk_id": cid, "text": doc, "metadata": meta}
            for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"])
        ]
        _source_file_cache[stem] = chunks
    return _source_file_cache[stem]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    get_settings()  # đảm bảo settings load được trước khi chạm Chroma

    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        items = json.load(f)
        
    heldout_items = []
    if os.path.exists("eval/datasets/qa_heldout_set.json"):
        with open("eval/datasets/qa_heldout_set.json", encoding="utf-8") as f:
            heldout_items = json.load(f)

    # Build lại từ đầu, KHÔNG merge với file qrels cũ: trộn nhãn sinh bởi 2 quy
    # tắc khác nhau (bản cũ có cả score=1 từ lần build trước) khiến không còn
    # biết một nhãn "relevant" nghĩa là gì.
    qrels: dict[str, dict[str, int]] = {}

    matched, no_source_file, no_chunk_match, multi_chunk = 0, [], [], []

    for item in items + heldout_items:
        if item["type"] != "in_scope":
            continue
        source_file = item.get("source_file") or item.get("metadata", {}).get("source_file", "")
        # Remove data/processed/ prefix if present
        if source_file.startswith("data/processed/"):
            source_file = source_file[len("data/processed/"):]
        if not source_file:
            # Câu sinh sau này có thể chưa chạy backfill_eval_source_file.py.
            # `evidence_chunk_id` do shorten_eval_ground_truth.py ghi ra đã được
            # verify là chunk chứa nguyên văn đoạn bằng chứng, nên dùng thẳng.
            evidence_chunk_id = item.get("evidence_chunk_id")
            if evidence_chunk_id:
                qrels[item["id"]] = {evidence_chunk_id: 2}
                item["relevant_chunk_ids"] = [evidence_chunk_id]
                matched += 1
                continue
            no_source_file.append(item["id"])
            continue

        needle = normalize_for_match(item["ground_truth_context"])
        chunks = _chunks_for_source_file(source_file)
        # CHỈ khớp theo hướng "chunk chứa trọn đoạn bằng chứng". Bản trước từng
        # nới thêm hướng ngược lại (`chunk in needle`) để chữa triệu chứng
        # ground_truth_context dài hơn cả chunk — nhưng làm vậy thì mọi chunk
        # lọt trong cửa sổ trích 2.000 ký tự đều bị gán relevant, tức nhãn đổi
        # nghĩa thành "nằm trong đoạn trích" chứ không còn là "trả lời được câu
        # hỏi", làm Recall bị thổi và Precision mất ý nghĩa. Gốc rễ đã xử lý ở
        # scripts/shorten_eval_ground_truth.py (rút bằng chứng xuống <= 400 ký tự).
        matches = [c["chunk_id"] for c in chunks if needle in normalize_for_match(c["text"])]

        if not matches:
            no_chunk_match.append(item["id"])
            continue

        qrels[item["id"]] = {cid: 2 for cid in matches}
        matched += 1
        if len(matches) > 1:
            multi_chunk.append((item["id"], matches))
        item["relevant_chunk_ids"] = matches

    total_in_scope = sum(1 for i in items + heldout_items if i["type"] == "in_scope")
    print(f"Đã map qrel: {matched}/{total_in_scope}")
    if multi_chunk:
        print(f"Câu khớp NHIỀU chunk (đáng chú ý, kiểm tra tay): {len(multi_chunk)}")
        for qid, ids in multi_chunk:
            print(f"  {qid}: {ids}")
    if no_source_file:
        print(f"Thiếu field source_file (chạy backfill_eval_source_file.py trước): {no_source_file}")
    if no_chunk_match:
        print(f"KHÔNG tìm thấy chunk nào chứa ground_truth_context (cần xem tay): {no_chunk_match}")

    if args.dry_run:
        return

    tmp_qrels = f"{QRELS_PATH}.tmp"
    with open(tmp_qrels, "w", encoding="utf-8") as f:
        json.dump(qrels, f, ensure_ascii=False, indent=2)
    os.replace(tmp_qrels, QRELS_PATH)
    print(f"\nĐã ghi {QRELS_PATH} ({len(qrels)} query)")

    tmp_path = f"{EVAL_SET_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, EVAL_SET_PATH)
    print(f"Đã ghi {EVAL_SET_PATH} (thêm relevant_chunk_ids)")
    
    if heldout_items:
        tmp_heldout = "eval/datasets/qa_heldout_set.json.tmp"
        with open(tmp_heldout, "w", encoding="utf-8") as f:
            json.dump(heldout_items, f, ensure_ascii=False, indent=2)
        os.replace(tmp_heldout, "eval/datasets/qa_heldout_set.json")
        print(f"Đã ghi eval/datasets/qa_heldout_set.json (thêm relevant_chunk_ids)")


if __name__ == "__main__":
    main()

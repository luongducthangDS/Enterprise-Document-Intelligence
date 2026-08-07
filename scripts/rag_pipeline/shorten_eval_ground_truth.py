#!/usr/bin/env python3
"""Rút `ground_truth_context` của các câu in_scope xuống một **evidence span**
ngắn (<= ~400 ký tự) nằm nguyên văn trong đúng 1 chunk.

## Vì sao

`ground_truth_context` hiện dài median 2.000 ký tự (max 2.530) trong khi
`chunk_max_chars` = 1.500 → **về mặt toán học không chunk nào chứa nổi nó**.
Đo được 78/128 câu rơi vào tình trạng này. Hệ quả:

- `eval_agent._context_found()` (dùng `needle in chunk_text`) luôn False cho
  những câu đó, bất kể retrieval đúng hay sai → pass rate sụp vì lỗi đo.
- `build_retrieval_qrels.py` phải nới quy tắc thành `chunk in needle`, khiến
  mọi chunk lọt trong cửa sổ trích 2.000 ký tự đều bị gán relevant → nhãn mất
  nghĩa, Recall bị thổi.

Đoạn bằng chứng ngắn thì luôn nằm gọn trong 1 chunk, và **sống sót qua mọi lần
đổi chunk size**: chunk_id đổi thì chỉ cần map lại bằng string match xác định,
không phải sinh lại dataset.

## Cách làm — trích chọn, không viết lại

LLM chỉ được **COPY nguyên văn** một đoạn có sẵn, và mọi output đều bị kiểm tra
`normalize(span) in normalize(chunk_text)`; không verbatim thì bỏ, lùi về cách
chọn xác định (chọn cửa sổ câu có độ trùng từ vựng cao nhất với
`expected_answer`). Đây là bài học từ vụ `ground_truth_context` bị GLM paraphrase
dù prompt đã yêu cầu trích nguyên văn (xem CLAUDE.md [2026-08-05]).

Chạy:
    python scripts/rag_pipeline/shorten_eval_ground_truth.py --dry-run
    python scripts/rag_pipeline/shorten_eval_ground_truth.py
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "eval", "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from _text_utils import normalize_for_match  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.retrieval.bm25 import BM25, tokenize  # noqa: E402
from src.services.fpt_client import chat_completion  # noqa: E402

CHUNKS_DIR = "data/chunks"
TARGET_FILES = ["eval/datasets/qa_eval_set.json", "eval/datasets/qa_heldout_set.json"]
MAX_SPAN_CHARS = 400
SENTENCE_RE = re.compile(r"(?<=[.!?:;])\s+|\n+")

_EXTRACT_SYSTEM = """Bạn trích đoạn bằng chứng cho bộ dữ liệu đánh giá hệ thống tìm kiếm tài liệu HR.

Nhiệm vụ: từ ĐOẠN TÀI LIỆU được cung cấp, COPY NGUYÊN VĂN đoạn ngắn nhất chứa câu trả lời cho câu hỏi.

Quy tắc tuyệt đối:
- CHỈ được sao chép y hệt từng ký tự từ đoạn tài liệu. KHÔNG viết lại, KHÔNG tóm tắt, KHÔNG sửa dấu câu, KHÔNG ghép các phần rời rạc.
- Đoạn copy phải LIỀN MẠCH (một khối liên tục trong tài liệu).
- Độ dài tối đa 400 ký tự, ưu tiên ngắn gọn nhưng đủ chứa thông tin trả lời.
- Chỉ trả về JSON, không giải thích."""

_EXTRACT_USER = """Câu hỏi: {question}

Câu trả lời mong đợi: {expected}

Đoạn tài liệu:
---
{passage}
---

Trả về JSON: {{"span": "<đoạn copy nguyên văn>"}}"""


def load_chunks() -> dict[str, list[dict]]:
    """{source_stem: [chunk...]} — đọc từ data/chunks (nguồn khớp với index)."""
    by_stem: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(os.path.join(CHUNKS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            chunks = json.load(f)
        if chunks:
            by_stem[chunks[0]["metadata"]["source_stem"]] = chunks
    return by_stem


_bm25 = None
_all_chunks: dict[str, dict] = {}


def _bm25_index(by_stem: dict[str, list[dict]]):
    """Chỉ mục BM25 trên toàn bộ chunk — dùng khi câu hỏi không có field
    `source_file` (bộ held-out và 40 câu mới sinh đều thiếu field này)."""
    global _bm25
    if _bm25 is None:
        for chunks in by_stem.values():
            for c in chunks:
                _all_chunks[c["metadata"]["chunk_id"]] = c
        ids = sorted(_all_chunks)
        _bm25 = BM25(ids, [_all_chunks[i]["text"] for i in ids])
    return _bm25


def candidate_chunks(item: dict, by_stem: dict[str, list[dict]]) -> list[dict]:
    """Các chunk có khả năng chứa bằng chứng: cùng tài liệu nguồn, xếp theo độ
    trùng từ vựng với ground_truth_context cũ. Không biết tài liệu nguồn thì
    tìm trên toàn corpus bằng BM25."""
    # Một số câu để `source_file` = None ở cấp trên nhưng vẫn khai trong
    # `metadata` — không đọc cả hai thì sẽ rơi xuống nhánh tìm toàn corpus và
    # có thể lấy bằng chứng từ TÀI LIỆU KHÁC cùng chủ đề (đã xảy ra với 2 câu
    # về đào tạo/BHYT), khiến qrels sau đó không khớp tài liệu nguồn đã khai.
    source_file = item.get("source_file") or item.get("metadata", {}).get("source_file", "") or ""
    stem = os.path.splitext(os.path.basename(source_file))[0]
    chunks = by_stem.get(stem)
    if not chunks:
        context = item.get("ground_truth_context", "")
        if not context:
            return []
        hits = _bm25_index(by_stem).top_k(context, k=3)
        return [_all_chunks[cid] for cid, _ in hits]
    needle_tokens = Counter(tokenize(item.get("ground_truth_context", "")))
    if not needle_tokens:
        return chunks[:3]

    def overlap(chunk: dict) -> int:
        return sum((Counter(tokenize(chunk["text"])) & needle_tokens).values())

    return sorted(chunks, key=overlap, reverse=True)[:3]


def find_containing_chunk(span: str, chunks: list[dict]) -> dict | None:
    needle = normalize_for_match(span)
    if len(needle) < 30:
        return None
    for chunk in chunks:
        if needle in normalize_for_match(chunk["text"]):
            return chunk
    return None


def deterministic_span(item: dict, chunk: dict) -> str:
    """Cửa sổ câu liên tiếp (<= MAX_SPAN_CHARS) trùng từ vựng nhiều nhất với
    expected_answer — không gọi LLM nên không có rủi ro bịa."""
    target = Counter(tokenize(item.get("expected_answer", "") + " " + item.get("question", "")))
    sentences = [s for s in SENTENCE_RE.split(chunk["text"]) if s.strip()]
    best, best_score = "", -1
    for i in range(len(sentences)):
        window = ""
        for j in range(i, len(sentences)):
            candidate = (window + " " + sentences[j]).strip() if window else sentences[j]
            if len(candidate) > MAX_SPAN_CHARS:
                break
            window = candidate
            score = sum((Counter(tokenize(window)) & target).values())
            if score > best_score:
                best, best_score = window, score
    return best or chunk["text"][:MAX_SPAN_CHARS]


def parse_json_block(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Không có JSON trong output: {raw[:150]}")
    return json.loads(text[start : end + 1])


def shorten_one(item: dict, by_stem: dict[str, list[dict]]) -> dict:
    old = item.get("ground_truth_context", "")
    chunks = candidate_chunks(item, by_stem)
    if not chunks:
        return {"id": item["id"], "status": "no_candidate_chunk"}

    settings = get_settings()
    passage = "\n\n".join(c["text"] for c in chunks[:2])[:6000]
    span = ""
    try:
        raw = chat_completion(
            _EXTRACT_SYSTEM,
            _EXTRACT_USER.format(
                question=item.get("question", ""),
                expected=item.get("expected_answer", ""),
                passage=passage,
            ),
            model=settings.llm_model,
            base_url=settings.fpt_base_url,
            api_key=settings.fpt_api_key,
            temperature=0.0,
        )
        span = (parse_json_block(raw).get("span") or "").strip()
    except Exception as e:  # noqa: BLE001 — lỗi 1 câu không được làm chết cả mẻ
        print(f"  [lỗi LLM] {item['id']}: {type(e).__name__}: {e}")

    chunk = find_containing_chunk(span, chunks) if span else None
    status = "llm_verbatim"
    if chunk is None:
        # LLM paraphrase hoặc ghép rời → bỏ, dùng cách chọn xác định.
        chunk = chunks[0]
        span = deterministic_span(item, chunk)
        status = "deterministic_fallback"
        if not find_containing_chunk(span, [chunk]):
            return {"id": item["id"], "status": "failed"}

    return {
        "id": item["id"],
        "status": status,
        "span": span,
        "chunk_id": chunk["metadata"]["chunk_id"],
        "old_len": len(old),
        "new_len": len(span),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", nargs="*", help="Chỉ xử lý các id câu hỏi này (vd qa_127 heldout_010)")
    args = parser.parse_args()

    by_stem = load_chunks()
    print(f"Đã nạp {sum(len(v) for v in by_stem.values())} chunk / {len(by_stem)} tài liệu")

    for path in TARGET_FILES:
        if not os.path.exists(path):
            print(f"[bỏ qua] không có {path}")
            continue
        with open(path, encoding="utf-8") as f:
            items = json.load(f)

        targets = [i for i in items if i.get("type") == "in_scope" and i.get("ground_truth_context")]
        if args.only:
            targets = [i for i in targets if i["id"] in args.only]
        if not targets:
            continue
        print(f"\n=== {path}: {len(targets)} câu in_scope ===")

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda i: shorten_one(i, by_stem), targets))

        by_id = {r["id"]: r for r in results}
        stats = Counter(r["status"] for r in results)
        lens = [r["new_len"] for r in results if r.get("new_len")]
        olds = [r["old_len"] for r in results if r.get("old_len")]
        print(f"  {dict(stats)}")
        if lens:
            print(f"  độ dài: {sum(olds)//len(olds)} → {sum(lens)//len(lens)} ký tự (max mới {max(lens)})")

        if args.dry_run:
            for r in results[:3]:
                if r.get("span"):
                    print(f"  ví dụ {r['id']} [{r['status']}] → {r['chunk_id']}: {r['span'][:120]}...")
            continue

        updated = 0
        for item in items:
            r = by_id.get(item.get("id"))
            if not r or not r.get("span"):
                continue
            item.setdefault("ground_truth_context_long", item["ground_truth_context"])
            item["ground_truth_context"] = r["span"]
            item["evidence_chunk_id"] = r["chunk_id"]
            item["evidence_source"] = r["status"]
            updated += 1

        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        with open(tmp, encoding="utf-8") as f:
            json.load(f)
        os.replace(tmp, path)
        print(f"  đã cập nhật {updated} câu → {path}")


if __name__ == "__main__":
    main()

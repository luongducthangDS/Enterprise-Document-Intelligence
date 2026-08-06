#!/usr/bin/env python3
"""Đo retrieval THUẦN (bỏ qua router/grade/rewrite/generate của agent) trên toàn
bộ eval/datasets/qa_eval_set.json — gọi thẳng embedding + Chroma Cloud, không đi
qua src/agents/graph.py, để tách bạch chất lượng retrieval khỏi hành vi lọc/rewrite
của agent (xem eval_agent.py cho eval end-to-end).

Tính 2 loại metric song song cho 60 câu in_scope (xem CLAUDE.md [2026-08-05]):

- **Chunk-level (qrel-based)**: so khớp `chunk_id` trả về từ Chroma với
  `eval/datasets/retrieval_qrels.json` (qrel xây bằng
  `scripts/build_retrieval_qrels.py` — deterministic, match `ground_truth_context`
  đã verify verbatim với chunk thật trong Chroma Cloud, KHÔNG dùng LLM đoán).
  Chính xác hơn substring match cũ (so ID, không so text) và hỗ trợ multi-chunk
  (relevance score, Recall@K/Precision@K/nDCG@K thay vì chỉ Hit Rate nhị phân).
- **Document-level Hit Rate**: so khớp field `source_file` (backfill qua
  `scripts/backfill_eval_source_file.py`) với metadata `source_file` của từng
  chunk retrieve được. Thô hơn (chỉ biết đúng FILE, không biết đúng đoạn), nhưng
  không bị ảnh hưởng bởi lỗi ranh giới chunking — dùng làm cận trên tham khảo.

40 câu còn lại (ambiguous/out_of_scope/competitor_comparison): KHÔNG có ground
truth để chấm đúng/sai — chỉ báo cáo distance của top-1 để tham khảo (câu hỏi
càng "lạc đề" thì distance top-1 kỳ vọng càng lớn, dùng để cân nhắc ngưỡng
retrieval_max_distance của grade_node, không phải để tính Hit Rate).

Chạy: python eval/scripts/eval_retrieval.py [--limit N] [--top-k 10]
"""
import argparse
import asyncio
import json
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.retrieval import _aembed_query, _collection  # noqa: E402

EVAL_SET_PATH = "eval/datasets/qa_eval_set.json"
QRELS_PATH = "eval/datasets/retrieval_qrels.json"
RESULTS_PATH = "eval/results/retrieval_eval_report.json"
HIT_RATE_KS = (1, 3, 5, 10)


def _first_doc_hit_rank(expected_source_file: str, chunk_source_files: list[str]) -> int:
    """Thứ hạng (1-based) của chunk đầu tiên có đúng source_file, 0 nếu không có."""
    if not expected_source_file:
        return 0
    for rank, sf in enumerate(chunk_source_files, start=1):
        if sf == expected_source_file:
            return rank
    return 0


def _recall_at_k(relevant: dict[str, int], retrieved_ids: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    hit = len(set(retrieved_ids[:k]) & relevant.keys())
    return hit / len(relevant)


def _precision_at_k(relevant: dict[str, int], retrieved_ids: list[str], k: int) -> float:
    if k == 0:
        return 0.0
    hit = len(set(retrieved_ids[:k]) & relevant.keys())
    return hit / k


def _ndcg_at_k(relevant: dict[str, int], retrieved_ids: list[str], k: int) -> float:
    dcg = sum(relevant.get(cid, 0) / math.log2(i + 1) for i, cid in enumerate(retrieved_ids[:k], start=1))
    ideal_scores = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum(score / math.log2(i + 1) for i, score in enumerate(ideal_scores, start=1))
    return dcg / idcg if idcg > 0 else 0.0


def _first_relevant_rank(relevant: dict[str, int], retrieved_ids: list[str]) -> int:
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in relevant:
            return rank
    return 0


async def _retrieve_raw(query: str, top_k: int, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        embedding = await _aembed_query(query)
        collection = _collection()
        result = await asyncio.to_thread(collection.query, query_embeddings=[embedding], n_results=top_k)
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    return {"ids": ids, "documents": documents, "metadatas": metadatas, "distances": distances}


async def _run_one(item: dict, top_k: int, qrels: dict, semaphore: asyncio.Semaphore) -> dict:
    raw = await _retrieve_raw(item["question"], top_k, semaphore)
    ids = raw["ids"]
    metadatas = raw["metadatas"]
    distances = raw["distances"]

    entry = {
        "id": item["id"],
        "type": item["type"],
        "category": item["category"],
        "question": item["question"],
        "top1_distance": distances[0] if distances else None,
        "top1_source_file": metadatas[0].get("source_file") if metadatas else None,
        "num_retrieved": len(ids),
    }

    if item["type"] == "in_scope":
        relevant = qrels.get(item["id"], {})
        rank = _first_relevant_rank(relevant, ids)
        entry["hit_rank"] = rank
        entry["reciprocal_rank"] = (1.0 / rank) if rank else 0.0
        entry["num_relevant"] = len(relevant)
        entry["recall_at_k"] = {f"recall@{k}": round(_recall_at_k(relevant, ids, k), 3) for k in HIT_RATE_KS}
        entry["precision_at_k"] = {f"precision@{k}": round(_precision_at_k(relevant, ids, k), 3) for k in HIT_RATE_KS}
        entry["ndcg_at_k"] = {f"ndcg@{k}": round(_ndcg_at_k(relevant, ids, k), 3) for k in HIT_RATE_KS}

        chunk_source_files = [m.get("source_file", "") for m in metadatas]
        doc_rank = _first_doc_hit_rank(item.get("source_file", ""), chunk_source_files)
        entry["doc_hit_rank"] = doc_rank
        entry["doc_hits"] = {f"doc_hit@{k}": bool(doc_rank and doc_rank <= k) for k in HIT_RATE_KS}
    else:
        entry["hit_rank"] = None
        entry["reciprocal_rank"] = None
        entry["num_relevant"] = None
        entry["recall_at_k"] = None
        entry["precision_at_k"] = None
        entry["ndcg_at_k"] = None
        entry["doc_hit_rank"] = None
        entry["doc_hits"] = None

    return entry


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Chỉ chạy N câu đầu (debug nhanh)")
    parser.add_argument("--top-k", type=int, default=10, help="Số chunk lấy về mỗi câu hỏi")
    parser.add_argument("--concurrency", type=int, default=5, help="Số câu chạy song song")
    args = parser.parse_args()

    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        items = json.load(f)
    if args.limit:
        items = items[: args.limit]

    qrels = {}
    if os.path.exists(QRELS_PATH):
        with open(QRELS_PATH, encoding="utf-8") as f:
            qrels = json.load(f)
    else:
        print(f"[CẢNH BÁO] Không tìm thấy {QRELS_PATH} — chạy scripts/build_retrieval_qrels.py trước. "
              "Metric chunk-level sẽ = 0 cho toàn bộ câu.")

    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    done = 0
    for coro in asyncio.as_completed([_run_one(item, args.top_k, qrels, semaphore) for item in items]):
        r = await coro
        results.append(r)
        done += 1
        if r["type"] == "in_scope":
            chunk_status = f"chunk_hit@{r['hit_rank']}" if r["hit_rank"] else "chunk_MISS"
            doc_status = f"doc_hit@{r['doc_hit_rank']}" if r.get("doc_hit_rank") else "doc_MISS"
            status = f"{chunk_status} {doc_status}"
        else:
            status = f"top1_dist={r['top1_distance']:.3f}" if r["top1_distance"] is not None else "n/a"
        print(f"[{done}/{len(items)}] {r['id']} ({r['type']}) {status}")

    results.sort(key=lambda r: r["id"])
    in_scope = [r for r in results if r["type"] == "in_scope"]
    other = [r for r in results if r["type"] != "in_scope"]

    print("\n=== Chunk-level Retrieval metrics (qrel-based, in_scope, n=%d) ===" % len(in_scope))
    summary: dict = {"in_scope_n": len(in_scope)}
    for k in HIT_RATE_KS:
        recall_vals = [r["recall_at_k"][f"recall@{k}"] for r in in_scope]
        precision_vals = [r["precision_at_k"][f"precision@{k}"] for r in in_scope]
        ndcg_vals = [r["ndcg_at_k"][f"ndcg@{k}"] for r in in_scope]
        summary[f"recall@{k}"] = round(sum(recall_vals) / len(recall_vals), 3) if recall_vals else 0.0
        summary[f"precision@{k}"] = round(sum(precision_vals) / len(precision_vals), 3) if precision_vals else 0.0
        summary[f"ndcg@{k}"] = round(sum(ndcg_vals) / len(ndcg_vals), 3) if ndcg_vals else 0.0
        multi_chunk_recall = sum(1 for v in recall_vals if v >= 1.0) / len(recall_vals) if recall_vals else 0.0
        summary[f"multi_chunk_recall@{k}"] = round(multi_chunk_recall, 3)
        print(
            f"Recall@{k}: {summary[f'recall@{k}']:.1%}  "
            f"Precision@{k}: {summary[f'precision@{k}']:.1%}  "
            f"nDCG@{k}: {summary[f'ndcg@{k}']:.3f}  "
            f"Multi-chunk Recall@{k}: {summary[f'multi_chunk_recall@{k}']:.1%}"
        )
    mrr = sum(r["reciprocal_rank"] for r in in_scope) / len(in_scope) if in_scope else 0.0
    summary["mrr"] = round(mrr, 3)
    print(f"MRR: {mrr:.3f}")

    with_source_file = [r for r in in_scope if r.get("doc_hits") is not None]
    if with_source_file:
        print(f"\n=== Document-level Hit Rate (in_scope có source_file, n={len(with_source_file)}) ===")
        for k in HIT_RATE_KS:
            hit_count = sum(1 for r in with_source_file if r["doc_hits"][f"doc_hit@{k}"])
            rate = hit_count / len(with_source_file)
            summary[f"doc_hit_rate@{k}"] = round(rate, 3)
            print(f"Doc Hit Rate@{k}: {hit_count}/{len(with_source_file)} ({rate:.1%})")
        missing_sf = len(in_scope) - len(with_source_file)
        if missing_sf:
            print(f"(Bỏ qua {missing_sf} câu chưa có field source_file — chạy scripts/backfill_eval_source_file.py)")

    if other:
        avg_top1_distance = sum(r["top1_distance"] for r in other if r["top1_distance"] is not None) / len(other)
        summary["other_n"] = len(other)
        summary["other_avg_top1_distance"] = round(avg_top1_distance, 3)
        print(f"\n=== Tham khảo (n={len(other)}, không có ground truth) ===")
        print(f"Distance top-1 trung bình (ambiguous/out_of_scope/competitor): {avg_top1_distance:.3f}")

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "top_k": args.top_k,
        "summary": summary,
        "results": results,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nĐã lưu chi tiết: {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

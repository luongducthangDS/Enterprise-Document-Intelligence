#!/usr/bin/env python3
"""Đánh giá khả năng RETRIEVAL của hệ thống trên bộ dữ liệu Phòng Kế toán.

Script này đo retrieval THUẦN (không qua router/grade/generate) trực tiếp lên
Chroma Cloud — cùng kiến trúc và cơ chế kết nối với eval_retrieval.py của HR:
  - Schema JSON của eval_accounting.json (dùng `query` thay vì `question`,
    `qrels` inline thay vì file qrels riêng).
  - Hai split: dev (25 queries) và heldout (10 queries).
  - 5 loại câu: single_chunk, multi_chunk, cross_document, scenario_reasoning,
    ambiguous/out_of_scope/edge_case (không có ground truth).
  - Tích hợp Domain Plugin Hooks (G1 Hybrid, G2 Query Expansion, G3 Dynamic Top-K).

Chạy:
    python eval/scripts/eval_accounting_retrieval.py [--split dev|heldout|all] [--top-k 10] [--collection hr_documents]

Output:
    eval/results/accounting_retrieval_report.json
"""
import argparse
import asyncio
import json
import math
import os
import sys
from datetime import datetime, timezone

# ── Path setup ──────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings  # noqa: E402
from src.ingestion.indexer import get_chroma_client, get_collection  # noqa: E402
from src.services.fpt_client import embed_batch  # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────────
EVAL_DATASET = "eval/datasets/eval_accounting.json"
RESULTS_PATH = "eval/results/accounting_retrieval_report.json"
HIT_RATE_KS = (1, 3, 5, 10)

# Các loại có ground truth qrel để đo metric
IN_SCOPE_TYPES = {"single_chunk", "multi_chunk", "cross_document", "scenario_reasoning", "table_lookup"}
# Loại chỉ báo distance tham khảo, không có ground truth
NO_GT_TYPES = {"ambiguous", "out_of_scope_or_personal", "edge_case_and_unanswerable"}


# ── Metric helpers ────────────────────────────────────────────────────────────
def _recall_at_k(qrels: dict, retrieved: list, k: int) -> float:
    if not qrels:
        return 0.0
    hit = len(set(retrieved[:k]) & set(qrels.keys()))
    return hit / len(qrels)


def _ndcg_at_k(qrels: dict, retrieved: list, k: int) -> float:
    dcg = sum(
        qrels.get(cid, 0) / math.log2(i + 1)
        for i, cid in enumerate(retrieved[:k], start=1)
    )
    ideal = sorted(qrels.values(), reverse=True)[:k]
    idcg = sum(s / math.log2(i + 1) for i, s in enumerate(ideal, start=1))
    return dcg / idcg if idcg > 0 else 0.0


def _mrr(qrels: dict, retrieved: list) -> float:
    for rank, cid in enumerate(retrieved, start=1):
        if cid in qrels:
            return 1.0 / rank
    return 0.0


def _first_hit_rank(qrels: dict, retrieved: list) -> int:
    for rank, cid in enumerate(retrieved, start=1):
        if cid in qrels:
            return rank
    return 0


from src.domains import get_matching_domain


# ── Embedding (sync wrapper) ──────────────────────────────────────────────────
def _embed_query(query: str, settings) -> list[float]:
    results = embed_batch(
        [query],
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
    )
    return results[0]


# ── Retrieve (async) ──────────────────────────────────────────────────────────
async def _retrieve(
    query: str, collection, top_k: int, semaphore: asyncio.Semaphore, settings, category: str | None = None
) -> dict:
    domain = get_matching_domain(query, category)
    effective_query = domain.expand_query(query) if domain else query
    effective_top_k = domain.get_top_k_override(query, top_k) if domain else top_k

    async with semaphore:
        embedding = await asyncio.to_thread(_embed_query, effective_query, settings)
        result = await asyncio.to_thread(
            collection.query,
            query_embeddings=[embedding],
            n_results=effective_top_k,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
    return {"ids": ids, "documents": documents, "metadatas": metadatas, "distances": distances}


# ── Evaluate one item ─────────────────────────────────────────────────────────
async def _eval_one(
    item: dict, collection, top_k: int, semaphore: asyncio.Semaphore, settings
) -> dict:
    query = item["query"]
    item_type = item["type"]
    qrels: dict = item.get("qrels", {})

    raw = await _retrieve(query, collection, top_k, semaphore, settings, category=item.get("category"))
    ids = raw["ids"]
    distances = raw["distances"]

    entry = {
        "id": item["id"],
        "query": query,
        "type": item_type,
        "category": item.get("category", ""),
        "split": item.get("split", "dev"),
        "top1_distance": distances[0] if distances else None,
        "top1_chunk_id": ids[0] if ids else None,
        "retrieved_ids": ids,
        "num_retrieved": len(ids),
        "num_relevant": len(qrels),
    }

    if item_type in IN_SCOPE_TYPES and qrels:
        hit_rank = _first_hit_rank(qrels, ids)
        entry["hit_rank"] = hit_rank
        entry["reciprocal_rank"] = (1.0 / hit_rank) if hit_rank else 0.0
        entry["recalls"] = {f"recall@{k}": round(_recall_at_k(qrels, ids, k), 4) for k in HIT_RATE_KS}
        entry["ndcgs"] = {f"ndcg@{k}": round(_ndcg_at_k(qrels, ids, k), 4) for k in HIT_RATE_KS}
        entry["hits"] = {f"hit@{k}": int(hit_rank > 0 and hit_rank <= k) for k in HIT_RATE_KS}

        # Kiểm tra xem top chunk có đúng source_file không?
        expected_files = set(os.path.splitext(f)[0] for f in item.get("source_files", []))
        retrieved_files = set()
        for m in raw["metadatas"]:
            sf = m.get("source_file", "")
            retrieved_files.add(os.path.splitext(os.path.basename(sf))[0])
        entry["doc_hit"] = bool(expected_files & retrieved_files)
        entry["missed_chunks"] = [cid for cid in qrels if cid not in ids]
        entry["is_in_scope"] = True
    else:
        # ambiguous / out_of_scope / edge_case: chỉ ghi distance tham khảo
        entry["hit_rank"] = None
        entry["reciprocal_rank"] = None
        entry["recalls"] = None
        entry["ndcgs"] = None
        entry["hits"] = None
        entry["doc_hit"] = None
        entry["missed_chunks"] = None
        entry["is_in_scope"] = False

    return entry


# ── Aggregate metrics ─────────────────────────────────────────────────────────
def _aggregate(results: list[dict]) -> dict:
    in_scope = [r for r in results if r["is_in_scope"] and r.get("num_relevant", 0) > 0]
    no_gt = [r for r in results if not r["is_in_scope"]]

    summary: dict = {
        "total": len(results),
        "in_scope_n": len(in_scope),
        "no_gt_n": len(no_gt),
    }

    if in_scope:
        for k in HIT_RATE_KS:
            hr = sum(r["hits"][f"hit@{k}"] for r in in_scope) / len(in_scope)
            rc = sum(r["recalls"][f"recall@{k}"] for r in in_scope) / len(in_scope)
            ndcg = sum(r["ndcgs"][f"ndcg@{k}"] for r in in_scope) / len(in_scope)
            summary[f"hit_rate@{k}"] = round(hr, 4)
            summary[f"recall@{k}"] = round(rc, 4)
            summary[f"ndcg@{k}"] = round(ndcg, 4)

        summary["mrr"] = round(
            sum(r["reciprocal_rank"] for r in in_scope) / len(in_scope), 4
        )
        summary["doc_hit_rate"] = round(
            sum(1 for r in in_scope if r["doc_hit"]) / len(in_scope), 4
        )

        # Breakdown theo type
        type_breakdown: dict = {}
        for item_type in IN_SCOPE_TYPES:
            grp = [r for r in in_scope if r["type"] == item_type]
            if grp:
                hr5 = sum(r["hits"].get("hit@5", 0) for r in grp) / len(grp)
                rc5 = sum(r["recalls"].get("recall@5", 0) for r in grp) / len(grp)
                type_breakdown[item_type] = {
                    "n": len(grp),
                    "hit_rate@5": round(hr5, 4),
                    "recall@5": round(rc5, 4),
                }
        summary["by_type"] = type_breakdown

        # Breakdown theo category
        cat_breakdown: dict = {}
        for r in in_scope:
            cat = r.get("category", "unknown")
            cat_breakdown.setdefault(cat, {"n": 0, "hits": 0, "recall": 0.0})
            cat_breakdown[cat]["n"] += 1
            cat_breakdown[cat]["hits"] += r["hits"].get("hit@5", 0)
            cat_breakdown[cat]["recall"] += r["recalls"].get("recall@5", 0)
        for cat, v in cat_breakdown.items():
            n = v["n"]
            summary["by_category"] = summary.get("by_category", {})
            summary["by_category"][cat] = {
                "n": n,
                "hit_rate@5": round(v["hits"] / n, 4),
                "recall@5": round(v["recall"] / n, 4),
            }

        # Failures (miss ở top-5)
        summary["miss_top5"] = [
            {"id": r["id"], "query": r["query"][:80], "missed_chunks": r["missed_chunks"]}
            for r in in_scope if r["hits"].get("hit@5", 0) == 0
        ]

    if no_gt:
        avg_dist = sum(r["top1_distance"] for r in no_gt if r["top1_distance"] is not None) / max(len(no_gt), 1)
        summary["no_gt_avg_top1_distance"] = round(avg_dist, 4)

    return summary


# ── Main ──────────────────────────────────────────────────────────────────────
async def main() -> None:
    parser = argparse.ArgumentParser(description="Eval retrieval trên tập dữ liệu Kế toán")
    parser.add_argument("--split", default="heldout", choices=["dev", "heldout", "all"],
                        help="Split để đo (mặc định heldout — held-out set là con số báo cáo chính thức)")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--out", default=RESULTS_PATH)
    parser.add_argument("--dataset", default=EVAL_DATASET)
    parser.add_argument("--collection", default="accounting_documents", help="Tên collection Chroma Cloud (mặc định 'accounting_documents')")
    parser.add_argument("--dev", action="store_true", help="Shorthand: chạy split=dev")
    args = parser.parse_args()

    if args.dev:
        args.split = "dev"

    settings = get_settings()

    # Kết nối Chroma Cloud (collection accounting_documents)
    client = get_chroma_client(settings)
    collection_name = args.collection or "accounting_documents"
    collection = get_collection(client, collection_name)
    print(f"[Chroma Cloud] Backend: {settings.vector_db_backend} | Collection: '{collection_name}' ({collection.count()} chunks)")

    # Load eval dataset
    dataset_path = os.path.join(_ROOT, args.dataset)
    with open(dataset_path, encoding="utf-8") as f:
        items: list[dict] = json.load(f)

    # Filter split
    if args.split != "all":
        before = len(items)
        items = [it for it in items if it.get("split", "dev") == args.split]
        print(f"[split={args.split}] {len(items)}/{before} queries")

    print(f"\nChạy retrieval eval: {len(items)} queries, top_k={args.top_k}, split={args.split}\n")

    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = [_eval_one(it, collection, args.top_k, semaphore, settings) for it in items]

    results: list[dict] = []
    done = 0
    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        done += 1
        if r["is_in_scope"]:
            hit5 = r["hits"]["hit@5"] if r["hits"] else "N/A"
            rc5 = f"{r['recalls']['recall@5']:.2f}" if r["recalls"] else "N/A"
            status = f"hit@5={hit5}  recall@5={rc5}  rank={r['hit_rank']}"
        else:
            dist = f"{r['top1_distance']:.3f}" if r["top1_distance"] is not None else "N/A"
            status = f"[no_gt] top1_dist={dist}"
        print(f"  [{done:02d}/{len(items)}] {r['id']} ({r['type']}) :: {status}")

    results.sort(key=lambda x: x["id"])
    summary = _aggregate(results)

    # ── Print summary ─────────────────────────────────────────────────────────
    in_scope_n = summary.get("in_scope_n", 0)
    print(f"\n{'='*65}")
    print(f"=== ACCOUNTING RETRIEVAL EVAL — split={args.split.upper()} | n={in_scope_n} ===")
    print(f"{'='*65}")
    if in_scope_n:
        for k in HIT_RATE_KS:
            print(
                f"  Hit Rate@{k:2d}: {summary.get(f'hit_rate@{k}', 0):.1%}  "
                f"Recall@{k:2d}: {summary.get(f'recall@{k}', 0):.1%}  "
                f"nDCG@{k:2d}: {summary.get(f'ndcg@{k}', 0):.3f}"
            )
        print(f"  MRR       : {summary.get('mrr', 0):.3f}")
        print(f"  Doc Hit   : {summary.get('doc_hit_rate', 0):.1%}")
        print()
        print("  Breakdown theo type (hit@5 / recall@5):")
        for t, v in summary.get("by_type", {}).items():
            print(f"    {t:<22s}: n={v['n']}  hit@5={v['hit_rate@5']:.1%}  recall@5={v['recall@5']:.1%}")
        print()
        print("  Breakdown theo category (hit@5 / recall@5):")
        for cat, v in summary.get("by_category", {}).items():
            print(f"    {cat:<30s}: n={v['n']}  hit@5={v['hit_rate@5']:.1%}  recall@5={v['recall@5']:.1%}")
        misses = summary.get("miss_top5", [])
        if misses:
            print(f"\n  ⚠️  MISS ở top-5 ({len(misses)} queries):")
            for m in misses:
                print(f"    [{m['id']}] {m['query']}")
                if m.get("missed_chunks"):
                    print(f"          Missed chunks: {m['missed_chunks'][:3]}")
    if summary.get("no_gt_n"):
        print(f"\n  No-GT queries: {summary['no_gt_n']} (avg top-1 distance={summary.get('no_gt_avg_top1_distance','N/A')})")
    print(f"{'='*65}\n")

    # Save report
    os.makedirs(os.path.dirname(os.path.join(_ROOT, args.out)), exist_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "split": args.split,
        "top_k": args.top_k,
        "dataset": args.dataset,
        "vector_db_backend": settings.vector_db_backend,
        "collection_name": collection_name,
        "collection_count": collection.count(),
        "summary": summary,
        "results": results,
    }
    out_path = os.path.join(_ROOT, args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Đã lưu report: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

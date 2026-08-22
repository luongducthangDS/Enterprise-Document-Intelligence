#!/usr/bin/env python3
"""Đo retrieval THUẦN (bỏ qua router/grade/rewrite/generate của agent) trên toàn
bộ eval/datasets/qa_eval_set.json — gọi thẳng embedding + Chroma Cloud, không đi
qua src/agents/graph.py, để tách bạch chất lượng retrieval khỏi hành vi lọc/rewrite
của agent (xem eval_agent.py cho eval end-to-end).

Tính 2 loại metric song song cho 60 câu in_scope (xem CLAUDE.md [2026-08-05]):

- **Chunk-level (qrel-based)**: so khớp `chunk_id` trả về từ Chroma với
  `eval/datasets/retrieval_qrels.json` (qrel xây bằng
  `scripts/rag_pipeline/build_retrieval_qrels.py` — deterministic, match `ground_truth_context`
  đã verify verbatim với chunk thật trong Chroma Cloud, KHÔNG dùng LLM đoán).
  Chính xác hơn substring match cũ (so ID, không so text) và hỗ trợ multi-chunk
  (relevance score, Recall@K/Precision@K/nDCG@K thay vì chỉ Hit Rate nhị phân).
- **Document-level Hit Rate**: so khớp field `source_file` (backfill qua
  `scripts/rag_pipeline/backfill_eval_source_file.py`) với metadata `source_file` của từng
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
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from _stats import bootstrap_ci, format_ci  # noqa: E402

from src.agents.nodes.retrieval import (  # noqa: E402
    _aembed_query,
    _bm25_index,
    _collection,
    _expand_retrieval_query,
    _provenance_filter,
)
from src.config import get_settings  # noqa: E402
from src.evaluation.retrieval_metrics import (  # noqa: E402
    expected_source_stems,
    first_doc_hit_rank,
    live_index_alignment,
)
from src.retrieval.hybrid import fuse_candidate_ids  # noqa: E402
from src.services.fpt_client import rerank  # noqa: E402
from src.security.models import UserContext, UserRole  # noqa: E402

EVAL_SET_PATH = "eval/datasets/qa_eval_set.json"
QRELS_PATH = "eval/datasets/retrieval_qrels.json"
RESULTS_PATH = "eval/results/retrieval_eval_report.json"
HIT_RATE_KS = (1, 3, 5, 10, 15, 20)

# Retrieval-quality benchmark phải nhìn thấy toàn bộ gold corpus. Đây chỉ là
# identity audit của evaluator; production retrieval vẫn dùng identity thật.
_EVAL_AUDIT_USER = UserContext(
    user_id="eval_retrieval",
    department="EXECUTIVE",
    role=UserRole.ADMIN,
    tenant_id="nexatech",
)


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


async def _retrieve_raw(
    query: str, top_k: int, semaphore: asyncio.Semaphore, use_rerank: bool = False, use_hybrid: bool = False
) -> dict:
    """`use_rerank=False`: đo dense retrieval thuần (embedding + Chroma).
    `use_rerank=True`: đo đúng thứ tự mà agent thực sự thấy (dense top-k rồi
    cross-encoder xếp lại) — nếu không có chế độ này thì eval và agent đang đo
    hai thứ khác nhau, và toàn bộ tác dụng của reranker vô hình với eval.
    `use_hybrid=True`: trộn thêm ứng viên BM25 (RRF) TRƯỚC khi rerank — dùng
    đúng `fuse_candidate_ids` mà `retrieval_node` dùng thật (không viết lại
    logic fusion riêng ở đây), để số đo phản ánh đúng code path production."""
    settings = get_settings()
    async with semaphore:
        query = _expand_retrieval_query(query)
        embedding = await _aembed_query(query)
        collection = _collection()
        where = _provenance_filter(settings, user_context=_EVAL_AUDIT_USER)
        query_kwargs = {"query_embeddings": [embedding], "n_results": top_k}
        if where:
            query_kwargs["where"] = where
        result = await asyncio.to_thread(collection.query, **query_kwargs)
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        if use_hybrid and ids:
            chunk_map = dict(zip(ids, zip(documents, metadatas, distances)))
            bm25 = await asyncio.to_thread(_bm25_index)
            fused_ids = fuse_candidate_ids(
                dense_ids=ids, bm25=bm25, query=query,
                bm25_top_k=settings.bm25_top_k, rrf_k=settings.rrf_k, fused_top_k=top_k,
            )
            missing_ids = [cid for cid in fused_ids if cid not in chunk_map]
            if missing_ids:
                fetched = await asyncio.to_thread(collection.get, ids=missing_ids, include=["documents", "metadatas"])
                for cid, doc, meta in zip(
                    fetched.get("ids") or [], fetched.get("documents") or [], fetched.get("metadatas") or []
                ):
                    # BM25-only candidate không có cosine distance thật — dùng
                    # None (không phải 0.0/số bịa) để không bị hiểu nhầm là gần
                    # nhất; distance chỉ dùng để BÁO CÁO ở entry, không ảnh
                    # hưởng thứ hạng (thứ hạng đã cố định bởi fuse_candidate_ids).
                    chunk_map[cid] = (doc, meta, None)
            ids = fused_ids
            documents = [chunk_map[cid][0] for cid in ids]
            metadatas = [chunk_map[cid][1] for cid in ids]
            distances = [chunk_map[cid][2] for cid in ids]

        if use_rerank and ids:
            settings = get_settings()
            try:
                ranked = await asyncio.to_thread(
                    rerank,
                    query,
                    list(documents),
                    model=settings.reranker_model,
                    base_url=settings.fpt_base_url,
                    api_key=settings.fpt_api_key,
                    top_n=len(documents),
                )
                order = [i for i, _ in ranked if 0 <= i < len(ids)]
                scores = {i: s for i, s in ranked}
                ids = [ids[i] for i in order]
                documents = [documents[i] for i in order]
                metadatas = [metadatas[i] for i in order]
                distances = [distances[i] for i in order]
                return {
                    "ids": ids, "documents": documents, "metadatas": metadatas,
                    "distances": distances, "scores": [scores[i] for i in order],
                }
            except Exception as e:  # noqa: BLE001
                print(f"[rerank lỗi, dùng thứ tự dense] {type(e).__name__}: {e}")

    return {"ids": ids, "documents": documents, "metadatas": metadatas, "distances": distances, "scores": None}


async def _run_one(
    item: dict, top_k: int, qrels: dict, semaphore: asyncio.Semaphore,
    use_rerank: bool = False, use_hybrid: bool = False,
) -> dict:
    raw = await _retrieve_raw(item["question"], top_k, semaphore, use_rerank=use_rerank, use_hybrid=use_hybrid)
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
        # Persist the actual ranking so a miss can be diagnosed without
        # repeating paid embedding/reranker calls.  Earlier reports kept only
        # the hit rank, which could not distinguish candidate-generation loss
        # from a reranker ordering problem.
        "retrieved_chunk_ids": ids,
        "retrieved_source_files": [metadata.get("source_file") for metadata in metadatas],
        "reranker_scores": raw["scores"],
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
        # Chunk-level relevance đến từ qrels, nên document-level relevance cũng
        # phải suy ra từ cùng qrels. Dùng một source_file legacy riêng lẻ từng
        # tạo nghịch lý chunk_hit nhưng doc_MISS khi qrel chấp nhận nhiều nguồn
        # canonical hoặc dataset còn giữ tên nguồn trước lúc migrate.
        expected_sources, source_label = expected_source_stems(item, relevant)
        doc_rank = first_doc_hit_rank(expected_sources, chunk_source_files)
        entry["expected_source_stems"] = sorted(expected_sources)
        entry["expected_source_label"] = source_label
        entry["doc_hit_rank"] = doc_rank
        entry["doc_hits"] = (
            {f"doc_hit@{k}": bool(doc_rank and doc_rank <= k) for k in HIT_RATE_KS}
            if expected_sources
            else None
        )
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
    parser.add_argument("--rerank", action="store_true", help="Đo SAU reranker (đúng thứ tự agent thấy) thay vì dense thuần")
    parser.add_argument(
        "--hybrid", action="store_true",
        help="Trộn thêm ứng viên BM25 (RRF) trước rerank — dùng đúng fuse_candidate_ids "
             "mà retrieval_node dùng thật (settings.use_hybrid KHÔNG ảnh hưởng script này, "
             "vì eval gọi thẳng Chroma chứ không qua retrieval_node)",
    )
    parser.add_argument("--out", default=RESULTS_PATH, help="Đường dẫn file báo cáo")
    parser.add_argument("--dataset", default=EVAL_SET_PATH, help="Bộ câu hỏi (mặc định qa_eval_set.json)")
    parser.add_argument("--qrels", default=QRELS_PATH, help="File qrels tương ứng với --dataset")
    parser.add_argument(
        "--split", default="dev", choices=["dev", "heldout", "all"],
        help="Tập con để đo. MẶC ĐỊNH 'dev' — held-out phải được giữ sạch, chỉ chạy khi thật sự cần con số cuối",
    )
    parser.add_argument(
        "--min-relevance", type=int, default=1, choices=[1, 2],
        help="Ngưỡng nhãn tính là relevant: 1 = cả chunk bổ trợ, 2 = chỉ chunk chứa câu trả lời",
    )
    parser.add_argument(
        "--allow-stale-qrels",
        action="store_true",
        help="Vẫn chạy khi qrel trỏ tới chunk không còn trong index; số đo chỉ có giá trị chẩn đoán",
    )
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        items = json.load(f)
    items = [item for item in items if not item.get("retired")]
    # Bộ retrieval eval set riêng dùng field `query` và `type` = single_chunk /
    # multi_chunk; bộ qa_eval_set dùng `question` và type = in_scope/... — quy
    # về một dạng để cùng 1 script đo được cả hai.
    for it in items:
        it.setdefault("question", it.get("query", ""))
        it.setdefault("category", it.get("category", ""))
        if it.get("type") in ("single_chunk", "multi_chunk"):
            it["retrieval_group"] = it["type"]
            it["type"] = "in_scope"
        # Bộ mới lưu `source_files` (số nhiều) vì câu rộng có thể trải trên
        # nhiều tài liệu. Doc Hit Rate chỉ có nghĩa khi câu chỉ có 1 tài liệu
        # nguồn — câu liên tài liệu để trống, script tự bỏ qua khi tính.
        if not it.get("source_file") and len(it.get("source_files") or []) == 1:
            it["source_file"] = it["source_files"][0]
    if args.split != "all":
        before = len(items)
        items = [it for it in items if it.get("split", "dev") == args.split]
        if len(items) != before:
            print(f"[split={args.split}] {len(items)}/{before} query")
    if args.limit:
        items = items[: args.limit]

    qrels = {}
    if os.path.exists(args.qrels):
        with open(args.qrels, encoding="utf-8") as f:
            qrels = json.load(f)
        if args.min_relevance > 1:
            qrels = {q: {c: s for c, s in rel.items() if s >= args.min_relevance} for q, rel in qrels.items()}
            qrels = {q: rel for q, rel in qrels.items() if rel}
    else:
        print(f"[CẢNH BÁO] Không tìm thấy {args.qrels} — chạy scripts/rag_pipeline/build_retrieval_qrels.py trước. "
              "Metric chunk-level sẽ = 0 cho toàn bộ câu.")

    # Fail trước khi gửi hàng chục query tốn phí nếu gold labels không còn tồn
    # tại trong chính collection đang được đo. Trước đây 160/189 qrel ID mất
    # khỏi index nhưng script vẫn chạy và báo Recall thấp như lỗi retriever.
    snapshot = await asyncio.to_thread(_collection().get, include=["metadatas"])
    alignment = live_index_alignment(
        items,
        qrels,
        set(snapshot.get("ids") or []),
        min_relevance=args.min_relevance,
    )
    if not alignment["benchmark_valid"]:
        print(
            "\n[QRELS/INDEX KHÔNG KHỚP] chỉ có "
            f"{alignment['available_qrel_chunk_labels']}/{alignment['qrel_chunk_labels']} gold chunk "
            f"còn trong index; {alignment['queries_with_any_available_qrel']}/"
            f"{alignment['scored_queries']} query còn ít nhất một gold chunk."
        )
        print("Chạy eval/scripts/audit_live_index_alignment.py để xem chi tiết.")
        if not args.allow_stale_qrels:
            print("Dừng trước khi gọi embedding/reranker. Dùng --allow-stale-qrels chỉ khi cần chẩn đoán.")
            raise SystemExit(2)

    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    done = 0
    for coro in asyncio.as_completed(
        [_run_one(item, args.top_k, qrels, semaphore, use_rerank=args.rerank, use_hybrid=args.hybrid) for item in items]
    ):
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
    # Query không có nhãn nào đạt ngưỡng relevance thì KHÔNG có đáp án đúng để
    # tìm — tính chúng là 0 điểm sẽ kéo mọi metric xuống một cách giả tạo. Loại
    # ra khỏi mẫu số và báo rõ số lượng (chúng cần người phân xử, không phải
    # bằng chứng hệ thống kém).
    scored = [r for r in results if r["type"] == "in_scope" and r.get("num_relevant")]
    unlabeled = [r["id"] for r in results if r["type"] == "in_scope" and not r.get("num_relevant")]
    if unlabeled:
        print(
            f"\n[loại khỏi metric] {len(unlabeled)} query không có nhãn nào đạt ngưỡng "
            f"min-relevance={args.min_relevance}: {unlabeled[:8]}"
        )
    in_scope = scored
    other = [r for r in results if r["type"] != "in_scope"]

    print(f"\n=== Chunk-level Retrieval metrics (qrel-based, in_scope, n={len(in_scope)}) ===")
    summary: dict = {"in_scope_n": len(in_scope), "excluded_no_qrel": len(unlabeled)}
    for k in HIT_RATE_KS:
        recall_vals = [r["recall_at_k"][f"recall@{k}"] for r in in_scope]
        precision_vals = [r["precision_at_k"][f"precision@{k}"] for r in in_scope]
        ndcg_vals = [r["ndcg_at_k"][f"ndcg@{k}"] for r in in_scope]
        summary[f"recall@{k}"] = round(sum(recall_vals) / len(recall_vals), 3) if recall_vals else 0.0
        summary[f"precision@{k}"] = round(sum(precision_vals) / len(precision_vals), 3) if precision_vals else 0.0
        summary[f"ndcg@{k}"] = round(sum(ndcg_vals) / len(ndcg_vals), 3) if ndcg_vals else 0.0
        multi_chunk_recall = sum(1 for v in recall_vals if v >= 1.0) / len(recall_vals) if recall_vals else 0.0
        summary[f"multi_chunk_recall@{k}"] = round(multi_chunk_recall, 3)
        hit_vals = [1.0 if (r["hit_rank"] and r["hit_rank"] <= k) else 0.0 for r in in_scope]
        hp, hlo, hhi = bootstrap_ci(hit_vals)
        rp, rlo, rhi = bootstrap_ci(recall_vals)
        summary[f"hit_rate@{k}"] = round(hp, 3)
        summary[f"hit_rate@{k}_ci"] = [round(hlo, 3), round(hhi, 3)]
        summary[f"recall@{k}_ci"] = [round(rlo, 3), round(rhi, 3)]
        print(
            f"Hit Rate@{k}: {format_ci(hp, hlo, hhi)}   "
            f"Recall@{k}: {format_ci(rp, rlo, rhi)}   "
            f"Precision@{k}: {summary[f'precision@{k}']:.1%}   "
            f"nDCG@{k}: {summary[f'ndcg@{k}']:.3f}   "
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
            print(f"(Bỏ qua {missing_sf} câu chưa có field source_file — chạy scripts/rag_pipeline/backfill_eval_source_file.py)")

    if other:
        avg_top1_distance = sum(r["top1_distance"] for r in other if r["top1_distance"] is not None) / len(other)
        summary["other_n"] = len(other)
        summary["other_avg_top1_distance"] = round(avg_top1_distance, 3)
        print(f"\n=== Tham khảo (n={len(other)}, không có ground truth) ===")
        print(f"Distance top-1 trung bình (ambiguous/out_of_scope/competitor): {avg_top1_distance:.3f}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "top_k": args.top_k,
        "reranked": args.rerank,
        "hybrid": args.hybrid,
        "dataset": args.dataset,
        "qrels": args.qrels,
        "min_relevance": args.min_relevance,
        "alignment": alignment,
        "summary": summary,
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nĐã lưu chi tiết: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

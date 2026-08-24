#!/usr/bin/env python3
"""Đánh giá retrieval riêng cho corpus Product.

Mặc định chạy lexical trên chunks local để có thể kiểm tra dataset không cần
credential/API. Đây là smoke benchmark; dùng --dense sau khi Product corpus đã
được index vào Chroma Cloud để đo dense retrieval production.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval.bm25 import BM25  # noqa: E402

DEFAULT_SET = "eval/datasets/product_retrieval_eval_set.json"
DEFAULT_QRELS = "eval/datasets/product_retrieval_qrels.json"
DEFAULT_CHUNKS = "data/product/chunks"


def _load_chunks(chunks_dir: str) -> dict[str, dict]:
    chunks = {}
    for path in sorted(Path(chunks_dir).glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            metadata = item["metadata"]
            chunks[metadata["chunk_id"]] = item
    return chunks


def _recall(relevant: dict[str, int], ranked: list[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant.keys()) / len(relevant) if relevant else 0.0


def _ndcg(relevant: dict[str, int], ranked: list[str], k: int) -> float:
    dcg = sum(relevant.get(cid, 0) / math.log2(rank + 1) for rank, cid in enumerate(ranked[:k], 1))
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum(score / math.log2(rank + 1) for rank, score in enumerate(ideal, 1))
    return dcg / idcg if idcg else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_SET)
    parser.add_argument("--qrels", default=DEFAULT_QRELS)
    parser.add_argument("--chunks-dir", default=DEFAULT_CHUNKS)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--out", default=None)
    parser.add_argument("--lexical", action="store_true", help="Explicit BM25 local mode (default)")
    parser.add_argument("--dense", action="store_true", help="Đo Chroma Cloud thay vì BM25 local")
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    qrels = json.loads(Path(args.qrels).read_text(encoding="utf-8"))
    if args.dense:
        from src.agents.nodes.retrieval import _aembed_query, _collection  # noqa: PLC0415
        from src.config import get_settings  # noqa: PLC0415

        import asyncio

        async def retrieve(question: str) -> list[str]:
            result = await asyncio.to_thread(
                _collection(get_settings().chroma_product_collection_name).query,
                query_embeddings=[await _aembed_query(question)],
                n_results=args.top_k,
                where={"department": "Product"},
            )
            return (result.get("ids") or [[]])[0]

    else:
        chunks = _load_chunks(args.chunks_dir)
        index = BM25(list(chunks), [item["text"] for item in chunks.values()])

        async def retrieve(question: str) -> list[str]:
            return [chunk_id for chunk_id, _ in index.top_k(question, k=args.top_k)]

    async def run() -> dict:
        import asyncio

        rows = []
        for item in dataset:
            ranked = await retrieve(item["question"])
            relevant = qrels.get(item["id"], {})
            row = {
                "id": item["id"],
                "type": item["type"],
                "feature": item["feature"],
                "owner": item["owner"],
                "retrieved_chunk_ids": ranked,
                "recall_at_k": _recall(relevant, ranked, args.top_k) if relevant else None,
                "ndcg_at_k": _ndcg(relevant, ranked, args.top_k) if relevant else None,
                "top1_source_file": chunks[ranked[0]]["metadata"]["source_file"] if not args.dense and ranked else None,
            }
            rows.append(row)
        scored = [row for row in rows if row["recall_at_k"] is not None]
        return {
            "dataset": args.dataset,
            "qrels": args.qrels,
            "mode": "dense" if args.dense else "bm25_local",
            "top_k": args.top_k,
            "queries": len(dataset),
            "in_scope_queries": len(scored),
            "mean_recall_at_k": sum(row["recall_at_k"] for row in scored) / len(scored) if scored else 0.0,
            "mean_ndcg_at_k": sum(row["ndcg_at_k"] for row in scored) / len(scored) if scored else 0.0,
            "rows": rows,
        }

    report = __import__("asyncio").run(run())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

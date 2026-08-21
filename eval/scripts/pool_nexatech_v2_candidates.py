#!/usr/bin/env python3
"""Pool dense/BM25 candidates for human qrel adjudication on benchmark v2.

This script does not call a judge and never promotes a candidate to gold.  It
only gathers a diverse review pool, including a source-constrained dense pass
so a miss by the global retriever does not hide potentially relevant chunks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.retrieval import (  # noqa: E402
    _aembed_query,
    _collection,
    _expand_retrieval_query,
    _provenance_filter,
)
from src.config import get_settings  # noqa: E402
from src.retrieval.bm25 import BM25  # noqa: E402


def source_stem_for_filter(source_file: str | None) -> str:
    """Preserve case because Chroma metadata equality is case-sensitive."""
    value = str(source_file or "").replace("\\", "/")
    return os.path.splitext(os.path.basename(value))[0]


def contextual_query(case: dict, turn: dict, by_id: dict[str, dict]) -> str:
    questions: list[str] = []
    parent_id = case.get("continues_case_id")
    visited: set[str] = set()
    while parent_id and parent_id not in visited:
        visited.add(parent_id)
        parent = by_id.get(parent_id)
        if not parent:
            break
        questions = [item["question"] for item in parent.get("turns", [])] + questions
        parent_id = parent.get("continues_case_id")
    questions.extend(item["question"] for item in case.get("turns", []) if item["turn"] <= turn["turn"])
    if len(questions) == 1:
        return questions[0]
    return "\n".join(["Ngữ cảnh hội thoại:", *[f"- {question}" for question in questions]])


def combine_where(base: dict | None, source_stem: str) -> dict:
    source_condition = {"source_stem": source_stem}
    if not base:
        return source_condition
    if set(base) == {"$and"}:
        return {"$and": [*base["$and"], source_condition]}
    return {"$and": [base, source_condition]}


def merge_candidates(
    dense_ids: list[str],
    bm25_ranked: list[tuple[str, float]],
    source_dense_ids: list[str],
) -> tuple[list[str], dict[str, dict]]:
    details: dict[str, dict] = {}
    for origin, ranked in (
        ("dense", [(chunk_id, None) for chunk_id in dense_ids]),
        ("bm25", bm25_ranked),
        ("expected_source_dense", [(chunk_id, None) for chunk_id in source_dense_ids]),
    ):
        for rank, (chunk_id, score) in enumerate(ranked, start=1):
            entry = details.setdefault(chunk_id, {"origins": {}})
            entry["origins"][origin] = {"rank": rank, "score": score}
    ordered = sorted(
        details,
        key=lambda chunk_id: (
            min(info["rank"] for info in details[chunk_id]["origins"].values()),
            chunk_id,
        ),
    )
    return ordered, details


async def pool_one(
    case: dict,
    turn: dict,
    by_id: dict[str, dict],
    collection,
    corpus: dict[str, dict],
    bm25: BM25,
    semaphore: asyncio.Semaphore,
    dense_k: int,
    bm25_k: int,
    source_k: int,
) -> dict:
    async with semaphore:
        raw_query = contextual_query(case, turn, by_id)
        query = _expand_retrieval_query(raw_query)
        embedding = await _aembed_query(query)
        base_where = _provenance_filter(get_settings())
        dense_result = await asyncio.to_thread(
            collection.query,
            query_embeddings=[embedding],
            n_results=dense_k,
            **({"where": base_where} if base_where else {}),
        )
        dense_ids = (dense_result.get("ids") or [[]])[0]
        bm25_ranked = await asyncio.to_thread(bm25.top_k, query, bm25_k)

        expected_stem = source_stem_for_filter(case.get("source_file"))
        source_dense_ids: list[str] = []
        if expected_stem:
            source_result = await asyncio.to_thread(
                collection.query,
                query_embeddings=[embedding],
                n_results=source_k,
                where=combine_where(base_where, expected_stem),
            )
            source_dense_ids = (source_result.get("ids") or [[]])[0]

        candidate_ids, details = merge_candidates(dense_ids, bm25_ranked, source_dense_ids)
        candidates = []
        for chunk_id in candidate_ids:
            chunk = corpus.get(chunk_id) or {}
            metadata = chunk.get("metadata") or {}
            text = str(chunk.get("text") or "")
            candidates.append(
                {
                    "chunk_id": chunk_id,
                    "source_file": metadata.get("source_file"),
                    "title": metadata.get("title"),
                    "heading_path": metadata.get("heading_path"),
                    "excerpt": text[:700],
                    **details[chunk_id],
                    "human_relevance": None,
                }
            )
        return {
            "id": f"{case['id']}_l{turn['turn']}",
            "case_id": case["id"],
            "turn": turn["turn"],
            "query": turn["question"],
            "contextual_query": raw_query,
            "expected_source_file": case.get("source_file"),
            "expected_behavior_raw": turn.get("expected_behavior_raw"),
            "expected_states": turn.get("expected_states") or [],
            "contract_flags": case.get("contract_flags") or [],
            "review_status": "pending_human_adjudication",
            "candidates": candidates,
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/datasets/nexatech_post_mvp_v2_dev.json")
    parser.add_argument("--out", default="eval/results/nexatech_post_mvp_v2_candidate_pool.json")
    parser.add_argument("--dense-k", type=int, default=12)
    parser.add_argument("--bm25-k", type=int, default=12)
    parser.add_argument("--source-k", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as handle:
        cases = json.load(handle)
    by_id = {case["id"]: case for case in cases}
    work = [
        (case, turn)
        for case in cases
        for turn in case.get("turns", [])
        if turn.get("qrel_status") == "pending_adjudication"
    ]

    collection = _collection()
    base_where = _provenance_filter(get_settings())
    snapshot = await asyncio.to_thread(
        collection.get,
        include=["documents", "metadatas"],
        **({"where": base_where} if base_where else {}),
    )
    corpus = {
        chunk_id: {"text": text, "metadata": metadata}
        for chunk_id, text, metadata in zip(
            snapshot.get("ids") or [],
            snapshot.get("documents") or [],
            snapshot.get("metadatas") or [],
        )
    }
    bm25 = BM25(list(corpus), [chunk["text"] for chunk in corpus.values()])
    semaphore = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(
        *[
            pool_one(
                case,
                turn,
                by_id,
                collection,
                corpus,
                bm25,
                semaphore,
                args.dense_k,
                args.bm25_k,
                args.source_k,
            )
            for case, turn in work
        ]
    )
    results.sort(key=lambda item: item["id"])
    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "status": "PENDING_HUMAN_ADJUDICATION",
        "dataset": args.dataset,
        "query_count": len(results),
        "index_chunk_count": len(corpus),
        "pooling": {
            "dense_k": args.dense_k,
            "bm25_k": args.bm25_k,
            "expected_source_dense_k": args.source_k,
            "judge_used": False,
        },
        "instructions": {
            "human_relevance": "Set each candidate to 2 (answers), 1 (supports), or 0 (irrelevant).",
            "promotion_rule": "Do not create qrels until contract_flags are resolved and every query is reviewed.",
        },
        "results": results,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, output)
    print(f"pooled={len(results)} index_chunks={len(corpus)} judge_used=False")
    print(f"saved={output}")


if __name__ == "__main__":
    asyncio.run(main())

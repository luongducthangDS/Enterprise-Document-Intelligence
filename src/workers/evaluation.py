"""Evaluation worker: chạy bộ eval qua agent thật, chấm điểm, ra quality gate (finding #7).

Cùng quy tắc chấm với eval/scripts/eval_agent.py (xem src/evaluation/scoring.py)
nhưng chạy được trong container agent — thư mục eval/ bị .dockerignore loại trừ
trừ eval/datasets, nên worker chỉ phụ thuộc dataset JSON, không phụ thuộc script.

Vòng đời run (QUEUED -> ... -> COMPLETED/FAILED) vẫn thuộc về Backend; agent chỉ
trả metrics + quality_gate để Backend ghi vào bảng evaluation_runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from src.agents.graph import agent
from src.config import Settings, get_settings
from src.evaluation.scoring import (
    aggregate_metrics,
    citation_scores,
    context_found,
    evaluate_quality_gate,
    judge_answer,
    passed_for_type,
)
from src.models.schemas import EvaluationJobRequest
from src.workers.jobs import ProgressCallback

logger = logging.getLogger(__name__)

# dataset_id (Backend cấp, xem backend/app/services/evaluation_service.py) ->
# (file câu hỏi, file qrels). qrels=None nghĩa là dataset tự mang
# evidence_chunk_id trong từng câu.
DATASET_FILES: dict[str, tuple[str, str | None]] = {
    "evalset_hr_v1": ("qa_eval_set.json", "retrieval_qrels.json"),
    "evalset_default": ("qa_eval_set.json", "retrieval_qrels.json"),
    "evalset_hr_v2": ("qa_heldout_set.json", None),
}


class EvaluationError(RuntimeError):
    """Lỗi nghiệp vụ của evaluation — thông điệp trả thẳng cho Backend."""


def load_dataset(dataset_id: str, settings: Settings) -> tuple[list[dict], dict]:
    if dataset_id not in DATASET_FILES:
        raise EvaluationError(
            f"dataset_id '{dataset_id}' không có trong agent. Hỗ trợ: {', '.join(sorted(DATASET_FILES))}."
        )

    dataset_file, qrels_file = DATASET_FILES[dataset_id]
    dataset_path = os.path.join(settings.eval_datasets_dir, dataset_file)
    if not os.path.exists(dataset_path):
        raise EvaluationError(f"Không tìm thấy file dataset: {dataset_path}")

    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)
    # Câu `retired` bị loại khỏi mọi phép tính: nguồn của chúng đã bị gỡ khỏi
    # corpus có chủ đích nên không còn evidence để chấm.
    items = [item for item in items if not item.get("retired")]

    qrels: dict = {}
    if qrels_file:
        qrels_path = os.path.join(settings.eval_datasets_dir, qrels_file)
        if os.path.exists(qrels_path):
            with open(qrels_path, encoding="utf-8") as f:
                qrels = json.load(f)
        else:
            logger.warning("Thiếu qrels %s — recall lùi về evidence_chunk_id/so chuỗi", qrels_path)

    return items, qrels


def effective_retrieval_k(settings: Settings) -> int:
    """Số chunk thực sự đưa vào generate — recall được đo trên đúng con số này."""
    return settings.rerank_top_k if settings.use_reranker else settings.retrieval_top_k


async def _run_one(item: dict, semaphore: asyncio.Semaphore, qrels: dict, settings: Settings) -> dict:
    """Bọc TOÀN BỘ trong 1 try/except: lỗi mạng thoáng qua ở bất kỳ bước nào
    (kể cả judge) chỉ hỏng đúng 1 câu, không giết cả run."""
    item_type = item["type"]
    base = {"id": item["id"], "type": item_type, "category": item.get("category")}
    async with semaphore:
        t0 = time.perf_counter()
        try:
            result = await agent.ainvoke({"query": item["question"]})
            latency_ms = (time.perf_counter() - t0) * 1000

            context_ok = False
            answer_ok = False
            has_citation = False
            citation_correctness = None
            if item_type == "in_scope":
                context_ok = context_found(item, result.get("retrieved_chunks", []), qrels)
                answer_ok = await judge_answer(
                    item["question"], result.get("response", ""), item.get("expected_answer", ""), settings
                )
                has_citation, citation_correctness = citation_scores(item, result.get("citations", []), qrels)

            passed = passed_for_type(item_type, result, context_ok=context_ok, answer_ok=answer_ok)
        except Exception as exc:  # noqa: BLE001 — ghi nhận lỗi thay vì crash cả batch
            logger.warning("Eval case %s lỗi: %s", item.get("id"), exc)
            return {**base, "error": f"{type(exc).__name__}: {exc}", "passed": False, "latency_ms": None}

    return {
        **base,
        "passed": passed,
        "intent": result.get("intent"),
        "escalate": result.get("escalate", False),
        "escalate_reason": result.get("escalate_reason"),
        "needs_clarification": result.get("needs_clarification", False),
        "confidence_score": result.get("confidence_score"),
        "context_found": context_ok,
        "answer_correct": answer_ok,
        "has_citation": has_citation,
        "citation_correctness": citation_correctness,
        "num_retrieved_chunks": len(result.get("retrieved_chunks", [])),
        "latency_ms": round(latency_ms, 1),
    }


async def run_evaluation(
    request: EvaluationJobRequest,
    progress: ProgressCallback,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()

    progress("LOADING_DATASET", 5)
    items, qrels = load_dataset(request.dataset_id, settings)
    if request.types:
        items = [item for item in items if item["type"] in request.types]
    if request.limit:
        items = items[: request.limit]
    if not items:
        raise EvaluationError("Không còn câu nào để chạy sau khi lọc types/limit.")

    concurrency = request.concurrency or settings.eval_concurrency
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict] = []

    progress("RUNNING", 10)
    for coro in asyncio.as_completed([_run_one(item, semaphore, qrels, settings) for item in items]):
        results.append(await coro)
        # 10% chuẩn bị + 85% chạy case, 5% cuối cho bước tổng hợp.
        progress("RUNNING", 10 + int(85 * len(results) / len(items)))

    results.sort(key=lambda r: r["id"])
    progress("SCORING", 96)

    by_type: dict[str, dict] = {}
    for r in results:
        bucket = by_type.setdefault(r["type"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += 1 if r["passed"] else 0
    for bucket in by_type.values():
        bucket["rate"] = round(bucket["passed"] / bucket["total"], 4) if bucket["total"] else None

    metrics = aggregate_metrics(results, effective_retrieval_k(settings))
    quality_gate, gate_details = evaluate_quality_gate(metrics, settings)
    errors = [r for r in results if r.get("error")]

    logger.info(
        "Evaluation %s: dataset=%s, %d/%d pass, gate=%s",
        request.job_id,
        request.dataset_id,
        sum(1 for r in results if r["passed"]),
        len(results),
        quality_gate,
    )
    return {
        "dataset_id": request.dataset_id,
        "total": len(results),
        "total_passed": sum(1 for r in results if r["passed"]),
        "error_count": len(errors),
        "summary_by_type": by_type,
        "metrics": metrics,
        "quality_gate": quality_gate,
        "quality_gate_details": gate_details,
        "agent_model": settings.llm_model,
        "judge_model": settings.judge_model,
        "index_version": settings.index_version,
        "results": results,
    }

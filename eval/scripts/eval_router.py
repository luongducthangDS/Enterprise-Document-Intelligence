#!/usr/bin/env python3
"""Đo riêng độ chính xác phân loại intent của router_node — chỉ gọi router_node
(1 LLM call/câu), không đi qua retrieval/generate, nên rẻ và nhanh, chạy được
trên cả 100 câu.

Mapping type trong qa_eval_set.json -> intent mong đợi:
- in_scope              -> hr_question
- ambiguous             -> ambiguous
- out_of_scope          -> out_of_scope_or_personal
- competitor_comparison -> out_of_scope_or_personal

(Không có mục "greeting" trong eval set — router chưa được test cho nhánh này
ở đây, cần bộ câu chào hỏi riêng nếu muốn đo.)

Chạy: python eval/scripts/eval_router.py [--limit N] [--concurrency N]
A/B model router (không sửa config file): ROUTER_MODEL=<tên> python eval/scripts/eval_router.py --out <file>
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.router import router_node  # noqa: E402
from src.config import get_settings  # noqa: E402

EVAL_SET_PATH = "eval/datasets/qa_eval_set.json"
RESULTS_PATH = "eval/results/router_eval_report.json"

TYPE_TO_EXPECTED_INTENT = {
    "in_scope": "hr_question",
    "ambiguous": "ambiguous",
    "out_of_scope": "out_of_scope_or_personal",
    "competitor_comparison": "out_of_scope_or_personal",
}
ALL_INTENTS = ["greeting", "hr_question", "ambiguous", "out_of_scope_or_personal"]


async def _run_one(item: dict, semaphore: asyncio.Semaphore) -> dict:
    expected = TYPE_TO_EXPECTED_INTENT[item["type"]]
    async with semaphore:
        t0 = time.perf_counter()
        result = await router_node({"query": item["question"]})
        latency_ms = (time.perf_counter() - t0) * 1000
    predicted = result.get("intent", "")
    return {
        "id": item["id"],
        "type": item["type"],
        "category": item["category"],
        "question": item["question"],
        "expected_intent": expected,
        "predicted_intent": predicted,
        "correct": predicted == expected,
        "latency_ms": round(latency_ms, 1),
    }


def _prf(results: list[dict], label: str) -> dict:
    tp = sum(1 for r in results if r["predicted_intent"] == label and r["expected_intent"] == label)
    fp = sum(1 for r in results if r["predicted_intent"] == label and r["expected_intent"] != label)
    fn = sum(1 for r in results if r["predicted_intent"] != label and r["expected_intent"] == label)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    support = tp + fn
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "support": support}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Chỉ chạy N câu đầu (debug nhanh)")
    parser.add_argument("--concurrency", type=int, default=5, help="Số câu chạy song song")
    parser.add_argument("--out", default=RESULTS_PATH, help="Đường dẫn file báo cáo (đổi khi A/B để không đè baseline)")
    args = parser.parse_args()

    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        items = json.load(f)
    if args.limit:
        items = items[: args.limit]

    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    done = 0
    for coro in asyncio.as_completed([_run_one(item, semaphore) for item in items]):
        r = await coro
        results.append(r)
        done += 1
        status = "OK" if r["correct"] else f"FAIL (dự đoán={r['predicted_intent']})"
        print(f"[{done}/{len(items)}] {r['id']} ({r['type']} -> {r['expected_intent']}) {status}")

    results.sort(key=lambda r: r["id"])
    total_correct = sum(1 for r in results if r["correct"])
    accuracy = total_correct / len(results) if results else 0.0

    settings = get_settings()
    router_model = settings.router_model or settings.llm_model
    print(f"\n=== Router Accuracy: {total_correct}/{len(results)} ({accuracy:.1%}) — model: {router_model} ===")

    latencies = sorted(r["latency_ms"] for r in results)
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))] if latencies else 0.0
    print(f"Latency router: p50={p50:.0f}ms p95={p95:.0f}ms")

    per_class = {label: _prf(results, label) for label in ALL_INTENTS}
    print("\n=== Precision / Recall / F1 theo lớp ===")
    for label, m in per_class.items():
        print(f"{label:28s} P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f} (support={m['support']})")

    confusion = Counter((r["expected_intent"], r["predicted_intent"]) for r in results)
    print("\n=== Confusion (expected -> predicted): count ===")
    for (expected, predicted), count in sorted(confusion.items()):
        if expected != predicted:
            print(f"  {expected} -> {predicted}: {count}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "router_model": router_model,
        "accuracy": round(accuracy, 3),
        "total": len(results),
        "total_correct": total_correct,
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "per_class": per_class,
        "confusion": {f"{e}->{p}": c for (e, p), c in confusion.items()},
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nĐã lưu chi tiết: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

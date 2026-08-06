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
"""
import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.router import router_node  # noqa: E402

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
        result = await router_node({"query": item["question"]})
    predicted = result.get("intent", "")
    return {
        "id": item["id"],
        "type": item["type"],
        "category": item["category"],
        "question": item["question"],
        "expected_intent": expected,
        "predicted_intent": predicted,
        "correct": predicted == expected,
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

    print(f"\n=== Router Accuracy: {total_correct}/{len(results)} ({accuracy:.1%}) ===")

    per_class = {label: _prf(results, label) for label in ALL_INTENTS}
    print("\n=== Precision / Recall / F1 theo lớp ===")
    for label, m in per_class.items():
        print(f"{label:28s} P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f} (support={m['support']})")

    confusion = Counter((r["expected_intent"], r["predicted_intent"]) for r in results)
    print("\n=== Confusion (expected -> predicted): count ===")
    for (expected, predicted), count in sorted(confusion.items()):
        if expected != predicted:
            print(f"  {expected} -> {predicted}: {count}")

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": round(accuracy, 3),
        "total": len(results),
        "total_correct": total_correct,
        "per_class": per_class,
        "confusion": {f"{e}->{p}": c for (e, p), c in confusion.items()},
        "results": results,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nĐã lưu chi tiết: {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

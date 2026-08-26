#!/usr/bin/env python3
"""Chạy sống eval/datasets/type_c_contract_set.json qua agent thật — xác nhận
NexaTech Type-C contract v3.1.0 (frozen): 20 canonical case + paraphrase + kịch
bản A/B/D1/D2/F. Tách khỏi tests/ (cùng convention với eval_agent.py) vì đây là
live integration tốn API, không chạy trong pytest suite mặc định.

Chạy: python eval/scripts/eval_type_c_contract.py [--concurrency N]
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.graph import agent  # noqa: E402
from src.agents.service import _derive_runtime_state  # noqa: E402

DATASET_PATH = "eval/datasets/type_c_contract_set.json"


async def _run_one(item: dict, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        try:
            result = await agent.ainvoke({"query": item["query"]})
        except Exception as e:  # noqa: BLE001
            return {
                **item,
                "error": str(e),
                "actual_state": "ERROR",
                "actual_reason_code": str(e),
                "passed": False,
            }


    state, reason_code = _derive_runtime_state(result)
    passed = state == item["expected_state"]
    if passed and "expected_reason_code" in item:
        passed = reason_code == item["expected_reason_code"]

    return {
        "id": item["id"],
        "category": item["category"],
        "expected_state": item["expected_state"],
        "expected_reason_code": item.get("expected_reason_code"),
        "actual_state": state,
        "actual_reason_code": reason_code,
        "intent": result.get("intent"),
        "escalate_reason": result.get("escalate_reason"),
        "citations_count": len(result.get("citations", [])),
        "response_preview": (result.get("response") or "")[:200],
        "passed": passed,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", default="eval/results/type_c_contract_report.json")
    args = parser.parse_args()

    with open(DATASET_PATH, encoding="utf-8") as f:
        items = json.load(f)

    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    done = 0
    for coro in asyncio.as_completed([_run_one(item, semaphore) for item in items]):
        r = await coro
        results.append(r)
        done += 1
        status = "OK" if r["passed"] else "FAIL"
        print(f"[{done}/{len(items)}] {status} {r['id']} ({r['category']}) -> {r['actual_state']}/{r.get('actual_reason_code')}")

    results.sort(key=lambda r: r["id"])

    by_category: dict[str, list[dict]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r)

    print("\n=== Kết quả theo category ===")
    summary = {}
    for cat, rs in sorted(by_category.items()):
        passed = sum(1 for r in rs if r["passed"])
        summary[cat] = {"passed": passed, "total": len(rs)}
        print(f"{cat}: {passed}/{len(rs)}")

    total_passed = sum(1 for r in results if r["passed"])
    print(f"\nTổng: {total_passed}/{len(results)}")

    type_c_results = by_category.get("Type C", [])
    type_c_passed = sum(1 for r in type_c_results if r["passed"])
    print(f"Type C canonical (20/20 invariant): {type_c_passed}/{len(type_c_results)}")

    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"\n=== {len(failed)} case FAIL ===")
        for r in failed:
            print(f"  {r['id']}: expected {r['expected_state']}/{r.get('expected_reason_code')}, "
                  f"got {r['actual_state']}/{r.get('actual_reason_code')} — {r['response_preview']}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "total": {"passed": total_passed, "total": len(results)}, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nBáo cáo đầy đủ: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

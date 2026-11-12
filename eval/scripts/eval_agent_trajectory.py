#!/usr/bin/env python3
"""Chấm QUỸ ĐẠO của agent, không chỉ câu trả lời cuối (eval_agent.py lo phần đó).

Phần A, chọn tool (chỉ AGENT_MODE=react), eval/datasets/agent_trajectory_set.json:
  must_call     : tool bắt buộc phải xuất hiện
  min_searches  : câu nhiều ý phải tìm ít nhất N lần
  max_searches  : câu đơn không được tìm quá N lần (đo "tìm thừa")
  expected_number: con số phải có trong câu trả lời (tool tính toán)

Phần B, chi phí + hiệu quả trên qa_eval_set in_scope (chạy được cả 2 mode):
  số lời gọi LLM (chat) và token mỗi câu, số bước tool, bước đầu tiên lấy được
  chunk gold (theo qrels), số lần search không đem về chunk mới.

Chạy:
  AGENT_MODE=react    python eval/scripts/eval_agent_trajectory.py
  AGENT_MODE=pipeline python eval/scripts/eval_agent_trajectory.py --skip-tools
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.graph import agent  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.evaluation.scoring import relevant_chunk_ids  # noqa: E402
from src.observability import llm_trace  # noqa: E402

IDENTITY = {"tenant_id": "nexatech", "user_id": "eval_traj", "department": "EXECUTIVE", "user_role": "ADMIN"}


async def run(question: str, rid: str) -> tuple[dict, list[dict], float]:
    with llm_trace.capture() as calls:
        t0 = time.perf_counter()
        state = await agent.ainvoke({"query": question, "request_id": rid, **IDENTITY})
        latency = time.perf_counter() - t0
    return state, calls, latency


def cost(calls: list[dict]) -> dict:
    chat = [c for c in calls if c.get("kind") == "chat"]
    return {
        "llm_calls": len(chat),
        "tokens": sum((c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0) for c in chat),
    }


def tool_check(item: dict, state: dict) -> list[str]:
    steps = state.get("agent_steps") or []
    tools = [s["tool"] for s in steps]
    searches = tools.count("search_policies")
    fails = []
    for t in item.get("must_call", []):
        if t not in tools:
            fails.append(f"thiếu {t}")
    if "min_searches" in item and searches < item["min_searches"]:
        fails.append(f"search {searches} < {item['min_searches']}")
    if "max_searches" in item and searches > item["max_searches"]:
        fails.append(f"search {searches} > {item['max_searches']}")
    if "expected_number" in item and item["expected_number"] not in (state.get("response") or ""):
        fails.append(f"thiếu số {item['expected_number']}")
    return fails


def trajectory(item: dict, state: dict, qrels: dict) -> dict:
    gold = relevant_chunk_ids(item, qrels)
    seen: set[str] = set()
    first_gold, redundant, n_search = None, 0, 0
    for i, s in enumerate(state.get("agent_steps") or [], 1):
        if s["tool"] != "search_policies":
            continue
        n_search += 1
        ids = set(s.get("chunk_ids") or [])
        if not ids - seen:
            redundant += 1
        if first_gold is None and gold and ids & gold:
            first_gold = n_search
        seen |= ids
    return {"n_search": n_search, "first_gold_search": first_gold, "redundant_search": redundant}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-tools", action="store_true", help="Bỏ phần A (dùng khi AGENT_MODE=pipeline)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()
    mode = get_settings().agent_mode
    sem = asyncio.Semaphore(args.concurrency)
    report: dict = {"mode": mode}

    if not args.skip_tools:
        items = json.load(open("eval/datasets/agent_trajectory_set.json", encoding="utf-8"))

        async def one_tool(it):
            async with sem:
                state, calls, lat = await run(it["question"], f"traj:{it['id']}")
            fails = tool_check(it, state)
            steps = [(s["tool"], s["args"]) for s in state.get("agent_steps") or []]
            print(f"[A] {'OK  ' if not fails else 'FAIL'} {it['id']} {fails} steps={steps}")
            return {"id": it["id"], "passed": not fails, "fails": fails, "steps": steps, **cost(calls), "latency_s": round(lat, 2)}

        res_a = await asyncio.gather(*[one_tool(it) for it in items])
        report["tool_choice"] = {"passed": sum(r["passed"] for r in res_a), "total": len(res_a), "results": res_a}
        print(f"\nA. Chọn tool đúng: {report['tool_choice']['passed']}/{len(res_a)}\n")

    items = [x for x in json.load(open("eval/datasets/qa_eval_set.json", encoding="utf-8")) if not x.get("retired") and x["type"] == "in_scope"]
    if args.limit:
        items = items[: args.limit]
    qrels = json.load(open("eval/datasets/retrieval_qrels.json", encoding="utf-8"))

    async def one(it):
        async with sem:
            try:
                state, calls, lat = await run(it["question"], f"traj:{it['id']}")
            except Exception as e:  # noqa: BLE001
                return {"id": it["id"], "error": str(e)}
        return {"id": it["id"], **cost(calls), "latency_s": round(lat, 2), **trajectory(it, state, qrels)}

    res_b = [r for r in await asyncio.gather(*[one(it) for it in items])]
    ok = [r for r in res_b if "error" not in r]

    def stat(key):
        vals = [r[key] for r in ok]
        return {"mean": round(statistics.mean(vals), 2), "p50": statistics.median(vals), "max": max(vals)}

    summary = {
        "n": len(ok),
        "errors": len(res_b) - len(ok),
        "llm_calls": stat("llm_calls"),
        "tokens": stat("tokens"),
        "latency_s": stat("latency_s"),
    }
    if mode == "react":
        golds = [r["first_gold_search"] for r in ok if r["first_gold_search"]]
        summary.update({
            "searches": stat("n_search"),
            "gold_found": f"{len(golds)}/{len(ok)}",
            "gold_at_first_search": sum(1 for g in golds if g == 1),
            "gold_only_after_retry": sum(1 for g in golds if g > 1),
            "redundant_searches_total": sum(r["redundant_search"] for r in ok),
            "questions_with_redundant_search": sum(1 for r in ok if r["redundant_search"]),
        })
    report["cost_trajectory"] = {"summary": summary, "results": res_b}
    print("B. Chi phí/quỹ đạo trên qa_eval_set in_scope:")
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    out = f"eval/results/agent_trajectory_{mode}_20261109.json"
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nĐã lưu {out}")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Benchmark so sánh kiến trúc agent trên eval/datasets/agent_benchmark.json.

Nhánh (--arms):
  rag            retrieve -> grade -> generate (RAG truyền thống, không router/rewrite/kiểm ảo giác)
  pipeline       workflow cố định hiện tại
  react          LLM tự chọn tool
  react_planner  react + planner (REACT_PLANNER)
  react_memory   react + bằng chứng lượt trước (chỉ chạy task followup)

Metric mỗi nhánh: task success, tool selection accuracy, argument accuracy, số bước,
tỷ lệ trong ngân sách bước, trajectory quality, hallucination (số trong câu trả lời
không có trong bằng chứng), p50/p95 latency, chi phí và số lời gọi LLM mỗi task.

  python eval/scripts/eval_agent_benchmark.py --split dev --arms rag,pipeline,react
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

DATASET = "eval/datasets/agent_benchmark.json"
TOOL_ARMS = {"react", "react_planner", "react_memory"}
ARM_GRAPH = {"rag": "rag", "pipeline": "pipeline", "react": "react", "react_planner": "react", "react_memory": "react"}


# ---------------------------------------------------------------- chấm điểm (hàm thuần)
def norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def outcome_checks(task: dict, answer: str, runtime_state: str, cited: set[str]) -> dict:
    exp = task["expect"]
    a = norm(answer)
    checks = {"state": runtime_state == exp["state"]}
    if "must_cite" in exp:
        checks["cite"] = set(exp["must_cite"]) <= cited
    if "cite_any" in exp:
        checks["cite"] = bool(set(exp["cite_any"]) & cited)
    if "must_contain" in exp:
        checks["contain"] = all(any(norm(v) in a for v in group) for group in exp["must_contain"])
    if "must_not_contain" in exp:
        checks["not_contain"] = not any(norm(v) in a for v in exp["must_not_contain"])
    if "must_not_cite" in exp:
        checks["not_cite"] = not (set(exp["must_not_cite"]) & cited)
    if exp.get("deliverable") == "comparison_table":
        checks["deliverable"] = sum(1 for line in answer.splitlines() if line.strip().startswith("|")) >= 3
    elif exp.get("deliverable") == "action_checklist":
        items = [line for line in answer.splitlines() if re.match(r"\s*([-*]|\d+[.)])\s+", line)]
        checks["deliverable"] = len(items) >= 2
    return checks


def _called(steps: list[dict], spec: str) -> bool:
    return any(s["tool"] in spec.split("|") for s in steps)


def tool_checks(task: dict, steps: list[dict]) -> dict:
    gold = task.get("gold_tools") or {}
    out: dict = {}
    if gold.get("must_call"):
        out["tool_selection"] = all(_called(steps, spec) for spec in gold["must_call"])
    if "min_searches" in gold:
        out["tool_selection"] = out.get("tool_selection", True) and sum(s["tool"] == "search_policies" for s in steps) >= gold["min_searches"]
    arg_ok: list[bool] = []
    for tool, want in (gold.get("args") or {}).items():
        calls = [s.get("args") or {} for s in steps if s["tool"] == tool and not s.get("error")]
        arg_ok.append(any(all(_arg_eq(c.get(k), v) for k, v in want.items()) for c in calls))
    if gold.get("compare_files"):
        calls = [s.get("args") or {} for s in steps if s["tool"] == "compare_documents" and not s.get("error")]
        arg_ok.append(any(set(gold["compare_files"]) <= set(c.get("source_files") or []) for c in calls))
    if gold.get("args_file"):
        calls = [s.get("args") or {} for s in steps if s["tool"] in ("get_document", "extract_structured") and not s.get("error")]
        arg_ok.append(any(c.get("source_file") == gold["args_file"] for c in calls))
    if arg_ok:
        out["argument"] = all(arg_ok)
    return out


def _arg_eq(got, want) -> bool:
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return abs(float(got) - float(want)) < 1e-6
    return got == want


def trajectory_metrics(task: dict, steps: list[dict]) -> dict:
    seen: set[str] = set()
    redundant = 0
    for s in steps:
        if s["tool"] != "search_policies":
            continue
        ids = set(s.get("chunk_ids") or [])
        if not ids - seen:
            redundant += 1
        seen |= ids
    errors = sum(1 for s in steps if s.get("error"))
    within = len(steps) <= task.get("max_steps", 99)
    quality = (int(errors == 0) + int(redundant == 0) + int(within)) / 3
    return {"steps": len(steps), "within_budget": within, "redundant_searches": redundant, "tool_errors": errors, "trajectory_quality": round(quality, 3)}


_NUM = re.compile(r"\d[\d.,/:]*\d|\d")
_SRC_LABEL = re.compile(r"\[\s*Nguồn\s*\d+\s*\]", re.I)


def ungrounded_numbers(answer: str, evidence: str, question: str) -> list[str]:
    """Số trong câu trả lời (>=2 chữ số) không xuất hiện trong bằng chứng hay câu hỏi."""
    pool = norm(evidence) + " " + norm(question)
    pool_digits = re.sub(r"[.,\s]", "", pool)
    bad = []
    for n in _NUM.findall(_SRC_LABEL.sub(" ", answer)):
        if len(re.sub(r"\D", "", n)) < 2:
            continue
        if n.lower() not in pool and re.sub(r"[.,]", "", n) not in pool_digits:
            bad.append(n)
    return bad


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]

    def rate(key, sub=None):
        vals = [(r[sub] if sub else r).get(key) for r in ok]
        vals = [v for v in vals if v is not None]
        return round(sum(map(bool, vals)) / len(vals), 3) if vals else None

    lat = sorted(r["latency_s"] for r in ok)
    cost = [r["cost_usd"] for r in ok if r.get("cost_usd") is not None]
    traj = [r["trajectory"] for r in ok if r.get("trajectory")]
    return {
        "n": len(rows),
        "errors": len(rows) - len(ok),
        "task_success": rate("success"),
        "tool_selection_accuracy": rate("tool_selection", "tools") if any(r.get("tools") for r in ok) else None,
        "argument_accuracy": rate("argument", "tools") if any(r.get("tools") for r in ok) else None,
        "avg_steps": round(statistics.mean(t["steps"] for t in traj), 2) if traj else None,
        "within_step_budget": round(statistics.mean(t["within_budget"] for t in traj), 3) if traj else None,
        "trajectory_quality": round(statistics.mean(t["trajectory_quality"] for t in traj), 3) if traj else None,
        "hallucination_rate": rate("hallucinated"),
        "p50_latency_s": round(statistics.median(lat), 2) if lat else None,
        "p95_latency_s": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 2) if lat else None,
        "cost_per_task_usd": round(statistics.mean(cost), 6) if cost else None,
        "llm_calls_per_task": round(statistics.mean(r["llm_calls"] for r in ok), 2) if ok else None,
        "by_category": {
            c: round(sum(r["success"] for r in ok if r["category"] == c) / max(1, sum(r["category"] == c for r in ok)), 3)
            for c in sorted({r["category"] for r in ok})
        },
    }


# ---------------------------------------------------------------- chạy agent
async def run_task(task: dict, arm: str, graphs: dict) -> dict:
    from src.agents.service import _derive_runtime_state, _sanitize_response
    from src.config import get_settings
    from src.observability import llm_trace, run_log

    settings = get_settings()
    settings.react_planner = arm == "react_planner"
    ident = {"tenant_id": "nexatech", "user_id": f"bench_{task['id']}", **task["identity"]}
    turns = task.get("turns") or [task["question"]]
    history: list[dict] = []
    memory: list = []
    t0 = time.perf_counter()
    with llm_trace.capture() as calls:
        for i, q in enumerate(turns):
            state_in = {"query": q, "history": list(history), "request_id": f"{arm}:{task['id']}:{i}", **ident}
            if arm == "react_memory" and memory:
                state_in["memory_chunks"] = memory
            state = await graphs[ARM_GRAPH[arm]].ainvoke(state_in)
            answer = _sanitize_response(state)
            history += [{"role": "user", "content": q}, {"role": "assistant", "content": answer}]
            memory = list(state.get("retrieved_chunks") or [])
    latency = time.perf_counter() - t0
    runtime_state, _ = _derive_runtime_state(state)
    cited = {c.get("source_file") for c in state.get("citations") or [] if c.get("source_file")}
    checks = outcome_checks(task, answer, runtime_state, cited)
    evidence = " ".join(c.get("text", "") for c in state.get("retrieved_chunks") or [])
    bad_numbers = ungrounded_numbers(answer, evidence, " ".join(turns)) if runtime_state == "ANSWER" else []
    steps = state.get("agent_steps") or []
    usage = run_log.llm_usage(calls)
    row = {
        "id": task["id"], "category": task["category"], "split": task["split"], "arm": arm,
        "success": all(checks.values()), "checks": checks, "state": runtime_state, "cited": sorted(cited),
        "hallucinated": bool(bad_numbers), "ungrounded_numbers": bad_numbers,
        "latency_s": round(latency, 2), "llm_calls": usage["chat_calls"], "cost_usd": usage["cost_usd"],
        "unpriced_tokens": usage["unpriced_tokens"], "answer": answer,
    }
    if arm in TOOL_ARMS:
        row["tools"] = tool_checks(task, steps)
        row["trajectory"] = trajectory_metrics(task, steps)
        row["steps"] = [{k: s.get(k) for k in ("tool", "args", "error")} for s in steps]
        row["plan"] = state.get("plan")
    return row


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "held_out", "all"], default="dev")
    ap.add_argument("--arms", default="rag,pipeline,react,react_planner,react_memory")
    ap.add_argument("--ids", default="", help="Chỉ chạy các id này (phân tách bằng dấu phẩy)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from src.agents.graph import build_graph

    data = json.load(open(DATASET, encoding="utf-8"))
    tasks = [t for t in data["tasks"] if args.split == "all" or t["split"] == args.split]
    if args.ids:
        tasks = [t for t in tasks if t["id"] in set(args.ids.split(","))]
    arms = [a for a in args.arms.split(",") if a]
    graphs = {g: build_graph(g) for g in {ARM_GRAPH[a] for a in arms}}
    out = args.out or f"eval/results/agent_benchmark_{args.split}_{datetime.now(UTC):%Y%m%d}.json"

    report: dict = {"dataset_version": data["version"], "split": args.split, "arms": {}, "results": []}
    for arm in arms:
        rows = []
        for t in tasks:
            if arm == "react_memory" and t["category"] != "followup":
                continue
            try:
                row = await run_task(t, arm, graphs)
            except Exception as e:  # noqa: BLE001 — một task lỗi không làm mất cả lượt chạy
                row = {"id": t["id"], "category": t["category"], "arm": arm, "error": f"{type(e).__name__}: {e}"[:300]}
            rows.append(row)
            mark = "ERR " if "error" in row else ("OK  " if row["success"] else "FAIL")
            print(f"[{arm}] {mark} {t['id']} {t['category']} {row.get('checks', row.get('error'))}", flush=True)
            report["results"] = [r for r in report["results"] if not (r["arm"] == arm and r["id"] == t["id"])] + [row]
            json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        report["arms"][arm] = summarize(rows)
        print(f"== {arm}: {json.dumps(report['arms'][arm], ensure_ascii=False)}", flush=True)
        json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Đã lưu: {out}")


if __name__ == "__main__":
    asyncio.run(main())

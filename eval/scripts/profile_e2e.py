#!/usr/bin/env python3
"""P3 — E2E latency profiling baseline. KHÔNG tối ưu gì, chỉ đo.

Mục tiêu: trả lời được "một request mất thời gian ở đâu, với tần suất bao nhiêu",
để chọn target optimization tiếp theo — chứ không phải để giảm latency ngay.

Ba con số phải tách bạch cho mỗi node (chỉ nhìn p50 là đọc sai target):

    conditional latency   node CHẠY thì mất bao lâu
    execution frequency   bao nhiêu % request thực sự chạy node đó
    expected contribution ~ frequency x mean cost  <- đây mới là thứ để xếp hạng

Ví dụ: một node p50 = 5s nhưng chỉ chạy 3% request đóng góp ít hơn hẳn node
p50 = 8s chạy trên 85% request.

Chạy: python eval/scripts/profile_e2e.py [--limit N] [--delay S]
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.graph import agent  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.observability import llm_trace  # noqa: E402

WORKLOAD = Path("eval/datasets/e2e_profiling_workload.json")
RESULTS = Path("eval/results/e2e_profile_baseline.json")

# Thứ tự hiển thị theo luồng graph, để bảng đọc như một timeline.
NODE_ORDER = [
    "condense", "router", "retrieve", "grade", "rewrite",
    "generate", "hallucination_check", "confidence", "escalate_ticket",
    "direct", "clarify", "finalize",
]


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = int(k)
    return s[f] if f + 1 >= len(s) else s[f] + (s[f + 1] - s[f]) * (k - f)


async def _profile_one(item: dict) -> dict:
    state = {"query": item["query"], "history": item.get("history") or []}
    node_durations: dict[str, float] = defaultdict(float)
    node_runs: dict[str, int] = defaultdict(int)
    final: dict = dict(state)

    # Mốc [bắt đầu, kết thúc) của từng lần chạy node, theo đúng thứ tự thực thi.
    # Dùng để gán mỗi lệnh gọi mạng vào node phát sinh ra nó.
    spans: list[tuple[str, float, float]] = []
    with llm_trace.capture() as calls:
        wall_start = time.perf_counter()
        previous = wall_start
        async for step in agent.astream(dict(state), stream_mode="updates"):
            for node_name, delta in step.items():
                now = time.perf_counter()
                node_durations[node_name] += (now - previous) * 1000
                node_runs[node_name] += 1
                spans.append((node_name, previous, now))
                previous = now
                final.update(delta)
        wall_ms = round((time.perf_counter() - wall_start) * 1000)

    # Gán node cho từng call. `occurrence` phân biệt lần chạy thứ mấy của cùng
    # một node — cần cho nhánh retry (generate chạy lại sau khi hallucination
    # FAIL), nếu không hai lần generate sẽ bị trộn làm một khi tính thống kê.
    seen: dict[str, int] = {}
    attributions: dict[int, int] = {}
    for node_name, start, end in spans:
        seen[node_name] = seen.get(node_name, 0) + 1
        for idx, c in enumerate(calls):
            if c.get("started_at") is not None and start <= c["started_at"] < end:
                c["node"] = node_name
                c["occurrence"] = seen[node_name]
                attributions[idx] = attributions.get(idx, 0) + 1
    for c in calls:
        c.setdefault("node", "unattributed")
        # Tỷ lệ ký tự output dành cho suy luận nội bộ thay vì cho người dùng.
        # KHÔNG phải tỷ lệ token: gateway không trả reasoning_tokens riêng, và
        # reasoning (tiếng Anh) có tỷ lệ token/ký tự khác answer (tiếng Việt).
        rc, ac = c.get("reasoning_chars"), c.get("answer_chars")
        if rc is not None and ac is not None and (rc + ac) > 0:
            c["reasoning_share_chars"] = round(rc / (rc + ac), 3)
            if c.get("completion_tokens"):
                c["chars_per_completion_token"] = round((rc + ac) / c["completion_tokens"], 2)
        if c.get("completion_tokens") and c["duration_ms"] > 0:
            c["throughput_tok_s"] = round(c["completion_tokens"] / (c["duration_ms"] / 1000), 1)

    # Ba invariant của phép gán theo thời gian. Đây là TEMPORAL ATTRIBUTION
    # HEURISTIC, không phải attribution tuyệt đối: nó chỉ đúng chừng nào graph
    # còn chạy tuần tự. Nếu sau này có node song song, background call hay
    # prefetch, một lệnh gọi có thể nằm trong nhiều span cùng lúc và phép gán
    # sai âm thầm. Ba cờ dưới đây để nó KHÔNG sai âm thầm.
    #
    # Muốn attribution chắc chắn thì node phải tự khai báo (ContextVar
    # current_node) — chưa cần chừng nào cả ba đều bằng 0.
    integrity = {
        "unattributed_calls": sum(1 for c in calls if c["node"] == "unattributed"),
        "multi_attributed_calls": sum(1 for v in attributions.values() if v > 1),
        "overlapping_node_spans": sum(
            1
            for i in range(len(spans))
            for j in range(i + 1, len(spans))
            if spans[i][1] < spans[j][2] and spans[j][1] < spans[i][2]
        ),
    }

    sum_nodes = round(sum(node_durations.values()))
    llm_calls = [c for c in calls if c["kind"] == "chat"]
    return {
        "id": item["id"],
        "category": item["category"],
        "query": item["query"][:90],
        "e2e_wall_ms": wall_ms,
        # Chênh lệch giữa wall-clock và tổng thời gian các node cho biết pipeline
        # có thực sự tuần tự không. Gần nhau = tuần tự; lệch lớn = có phần chạy
        # song song hoặc thời gian chờ nằm ngoài node.
        "sum_node_ms": sum_nodes,
        "unaccounted_ms": wall_ms - sum_nodes,
        "nodes": {k: round(v) for k, v in node_durations.items()},
        "node_runs": dict(node_runs),
        "llm_call_count": len(llm_calls),
        "network_call_count": len(calls),
        "retry_calls": sum(1 for c in calls if c["attempts"] > 1),
        "prompt_tokens": sum(c["prompt_tokens"] or 0 for c in llm_calls),
        "completion_tokens": sum(c["completion_tokens"] or 0 for c in llm_calls),
        "calls": calls,
        "attribution_integrity": integrity,
        "outcome": {
            "intent": final.get("intent"),
            "answerable": final.get("answerable"),
            "hallucination_passed": final.get("hallucination_passed"),
            "hallucination_retry_count": final.get("hallucination_retry_count", 0),
            "rewrite_count": final.get("rewrite_count", 0),
            "escalate": final.get("escalate", False),
            "needs_clarification": final.get("needs_clarification", False),
            "confidence_score": final.get("confidence_score"),
            "n_chunks": len(final.get("retrieved_chunks", []) or []),
        },
    }


def _node_table(rows: list[dict]) -> list[dict]:
    total = len(rows)
    e2e_mean = statistics.mean([r["e2e_wall_ms"] for r in rows])
    out = []
    seen = {n for r in rows for n in r["nodes"]}
    for node in NODE_ORDER + sorted(seen - set(NODE_ORDER)):
        if node not in seen:
            continue
        durations = [r["nodes"][node] for r in rows if node in r["nodes"]]
        exec_pct = 100 * len(durations) / total
        mean_when_run = statistics.mean(durations)
        # Expected contribution: chi phí TRUNG BÌNH TRÊN MỌI REQUEST, kể cả
        # request không chạy node đó. Đây mới là đại lượng cộng lại ra E2E.
        expected = mean_when_run * len(durations) / total
        out.append({
            "node": node,
            "exec_pct": round(exec_pct, 1),
            "n_exec": len(durations),
            "p50_ms": round(_pct(durations, 50)),
            "p95_ms": round(_pct(durations, 95)),
            "mean_ms": round(mean_when_run),
            "max_ms": round(max(durations)),
            "expected_ms": round(expected),
            "share_of_e2e_pct": round(100 * expected / e2e_mean, 1),
        })
    return sorted(out, key=lambda x: -x["expected_ms"])


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--out", default=str(RESULTS))
    args = parser.parse_args()

    payload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    items = payload["requests"][: args.limit] if args.limit else payload["requests"]
    settings = get_settings()
    print(f"{len(items)} request · workload {payload['version']}", flush=True)

    rows = []
    for n, item in enumerate(items, 1):
        try:
            rows.append(await _profile_one(item))
        except Exception as e:  # noqa: BLE001 — một request lỗi không được giết cả lần đo
            print(f"  [{n}/{len(items)}] {item['id']} LỖI: {type(e).__name__}: {e}", flush=True)
            continue
        r = rows[-1]
        print(
            f"  [{n}/{len(items)}] {r['id']} {r['category']:<24} "
            f"{r['e2e_wall_ms']:>6}ms · {r['llm_call_count']} LLM call · "
            f"{r['completion_tokens']} completion tok",
            flush=True,
        )
        await asyncio.sleep(args.delay)

    e2e = [r["e2e_wall_ms"] for r in rows]
    nodes = _node_table(rows)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "P3 baseline — chỉ đo, chưa tối ưu. Dùng để chọn target optimization.",
        "workload": {"file": str(WORKLOAD), "version": payload["version"], "n": len(rows)},
        "config": {
            "thinking_router": settings.thinking_router,
            "thinking_condense": settings.thinking_condense,
            "thinking_generation": settings.thinking_generation,
            "thinking_hallucination": settings.thinking_hallucination,
            "llm_model": settings.llm_model,
            "router_model": settings.router_model,
            "use_reranker": settings.use_reranker,
            "retrieval_top_k": settings.retrieval_top_k,
            "rerank_top_k": settings.rerank_top_k,
        },
        "e2e": {
            "p50_ms": round(_pct(e2e, 50)), "p75_ms": round(_pct(e2e, 75)),
            "p90_ms": round(_pct(e2e, 90)), "p95_ms": round(_pct(e2e, 95)),
            "mean_ms": round(statistics.mean(e2e)), "max_ms": max(e2e),
            "over_30s_pct": round(100 * sum(1 for x in e2e if x > 30000) / len(e2e), 1),
            "over_60s_pct": round(100 * sum(1 for x in e2e if x > 60000) / len(e2e), 1),
        },
        "requests_with_retry_pct": round(100 * sum(1 for r in rows if r["retry_calls"]) / len(rows), 1),
        "critical_path": {
            "mean_sum_node_ms": round(statistics.mean([r["sum_node_ms"] for r in rows])),
            "mean_wall_ms": round(statistics.mean(e2e)),
            "mean_unaccounted_ms": round(statistics.mean([r["unaccounted_ms"] for r in rows])),
            "note": "sum_node ~ wall => pipeline gần như tuần tự, không có phần chạy song song đáng kể.",
        },
        "nodes": nodes,
        "by_category": {
            cat: {
                "n": len([r for r in rows if r["category"] == cat]),
                "e2e_p50_ms": round(_pct([r["e2e_wall_ms"] for r in rows if r["category"] == cat], 50)),
                "mean_llm_calls": round(
                    statistics.mean([r["llm_call_count"] for r in rows if r["category"] == cat]), 1
                ),
            }
            for cat in sorted({r["category"] for r in rows})
        },
        "results": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Cảnh báo NGAY nếu phép gán theo thời gian không còn đáng tin — im lặng ở
    # đây nghĩa là mọi bảng thống kê theo node phía dưới đều đáng ngờ.
    broken = {
        k: sum(r["attribution_integrity"][k] for r in rows)
        for k in ("unattributed_calls", "multi_attributed_calls", "overlapping_node_spans")
    }
    report["attribution_integrity_total"] = broken
    if any(broken.values()):
        print(f"\n!!! ATTRIBUTION KHÔNG SẠCH: {broken} — số liệu theo node KHÔNG đáng tin", flush=True)
    else:
        print("\nAttribution: sạch (0 unattributed · 0 multi-attributed · 0 span chồng lấn)")

    e = report["e2e"]
    print(f"\n=== E2E (n={len(rows)}) ===")
    print(f"  p50={e['p50_ms']}ms  p75={e['p75_ms']}ms  p90={e['p90_ms']}ms  p95={e['p95_ms']}ms")
    print(f"  mean={e['mean_ms']}ms  max={e['max_ms']}ms  >30s={e['over_30s_pct']}%  >60s={e['over_60s_pct']}%")
    print(f"  request có retry: {report['requests_with_retry_pct']}%")
    cp = report["critical_path"]
    print(f"  critical path: sum(node)={cp['mean_sum_node_ms']}ms vs wall={cp['mean_wall_ms']}ms "
          f"(ngoài node: {cp['mean_unaccounted_ms']}ms)")
    print(f"\n{'Node':<22}{'Exec%':>7}{'p50':>8}{'p95':>9}{'mean':>8}{'max':>9}{'Expected':>10}{'%E2E':>7}")
    print("-" * 80)
    for r in nodes:
        print(f"{r['node']:<22}{r['exec_pct']:>6.0f}%{r['p50_ms']:>8}{r['p95_ms']:>9}"
              f"{r['mean_ms']:>8}{r['max_ms']:>9}{r['expected_ms']:>10}{r['share_of_e2e_pct']:>6.0f}%")
    print(f"\nĐã lưu: {args.out}")


asyncio.run(main())

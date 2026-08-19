#!/usr/bin/env python3
"""P4B Tier 2 — A/B `thinking_generation` ON vs OFF, có downstream veto.

Thiết kế bám đúng ba bài học đã trả giá để có:

1. ISOLATE, không rerun cả graph. Chạy pipeline tới hết `grade` MỘT lần để lấy
   chunks, freeze lại, rồi gọi `generate_node` hai lần trên CÙNG input. Rerun cả
   graph sẽ để retrieval/router thay đổi giữa hai nhánh và làm bẩn attribution.

2. PAIRED + RANDOMIZE thứ tự trong từng cặp. Gateway biến động mạnh (đã đo:
   `retrieve` ×3,9 giữa hai phiên), nên so hai lần chạy tách biệt là vô nghĩa.
   Randomize A→B / B→A để lần gọi thứ hai không luôn được hưởng connection
   warming.

3. DOWNSTREAM VETO. `generate` nhanh hơn mà làm hallucination FAIL nhiều hơn thì
   E2E vẫn chậm hơn: đo được ở P4B Tier 1 rằng lần generate thứ hai tốn xấp xỉ
   lần đầu (p50 4,88s vs 4,71s), nên mỗi FAIL mất gần trọn một generate + một
   check.

Chạy: python eval/scripts/eval_p4b_generate_ab.py [--limit N]
"""
import argparse
import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.condense import condense_node  # noqa: E402
from src.agents.nodes.generation import (  # noqa: E402
    INSUFFICIENT_MARKER,
    generate_node,
    hallucination_check_node,
)
from src.agents.nodes.retrieval import grade_node, retrieval_node  # noqa: E402
from src.agents.nodes.router import router_node  # noqa: E402
from src.config import get_settings  # noqa: E402

WORKLOAD = Path("eval/datasets/e2e_profiling_workload.json")
QA_SET = Path("eval/datasets/qa_eval_set.json")
RESULTS = Path("eval/results/p4b_generate_ab.json")
SEED = 20260813

# Số kèm đơn vị — dùng để bắt "bịa số liệu": số xuất hiện trong câu trả lời mà
# KHÔNG có trong context là dấu hiệu mạnh nhất của wrong confident answer, và
# đo được bằng máy nên không phụ thuộc judge.
# Bản đầu dùng `\d+(?:[.,]\d+)?` nên CẮT SAI số Việt Nam nhiều dấu ngăn nghìn:
# "5.310.000 đồng" bị bắt thành "310.000 đồng", rồi tất nhiên không khớp context
# và bị đếm là bịa số. Phải bắt trọn cụm số, và chặn đầu bằng lookbehind để
# không khớp từ giữa một số dài hơn.
_NUMBER = re.compile(
    r"(?<![\d.,])\d[\d.,]*\s*(?:%|ngày|tháng|năm|giờ|tuần|lần|triệu|đồng|vnđ)", re.IGNORECASE
)
_CITATION = re.compile(r"\[Nguồn([^\]]*)\]", re.IGNORECASE)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _grade_answer(answer: str, chunks: list[dict], expected_keywords: list[str]) -> dict:
    """Chấm bằng tín hiệu xác định. Ba nhóm, không nhóm nào dùng LLM judge."""
    context = _norm(" ".join(c["text"] for c in chunks))
    low = _norm(answer)

    cited: list[int] = []
    for m in _CITATION.finditer(answer):
        cited += [int(x) for x in re.findall(r"\d+", m.group(1))]
    invalid_citations = [n for n in cited if not (1 <= n <= len(chunks))]

    # Số trong câu trả lời mà không truy được về context -> nghi bịa.
    ungrounded = [m.group(0) for m in _NUMBER.finditer(low) if _norm(m.group(0)) not in context]

    has_sentinel = INSUFFICIENT_MARKER in answer
    return {
        # GROUNDING
        "has_citation": bool(cited) or has_sentinel,
        "citations_valid": not invalid_citations,
        "no_ungrounded_number": not ungrounded,
        # CORRECTNESS (chỉ khi có ground truth)
        "answer_keywords_hit": (not expected_keywords)
        or any(_norm(k) in low for k in expected_keywords),
        # SENTINEL
        "sentinel_consistent": (not has_sentinel) or len(answer) < 600,
        "non_empty": bool(answer.strip()),
        "_ungrounded": ungrounded,
        "_invalid_citations": invalid_citations,
        "_has_sentinel": has_sentinel,
    }


async def _prepare_inputs(items: list[dict]) -> list[dict]:
    """Chạy pipeline tới hết `grade` một lần để freeze input cho generate."""
    prepared = []
    for n, item in enumerate(items, 1):
        state: dict = {"query": item["query"], "history": item.get("history") or []}
        state.update(await condense_node(dict(state)))
        state.update(await router_node(dict(state)))
        if state.get("intent") != "hr_question":
            continue
        state.update(await retrieval_node(dict(state)))
        state.update(grade_node(dict(state)))
        if not state.get("retrieved_chunks"):
            continue
        prepared.append(
            {
                "id": item["id"],
                "category": item["category"],
                "query": item["query"],
                "expected_keywords": item.get("expected_keywords") or [],
                "state": {
                    "query": state["query"],
                    "condensed_query": state.get("condensed_query"),
                    "retrieved_chunks": state["retrieved_chunks"],
                },
            }
        )
        print(f"  [{n}/{len(items)}] {item['id']}: {len(state['retrieved_chunks'])} chunk", flush=True)
        await asyncio.sleep(0.5)
    return prepared


async def _run_generate(state: dict, thinking: bool) -> dict:
    settings = get_settings()
    original = settings.thinking_generation
    settings.thinking_generation = thinking
    try:
        t0 = time.perf_counter()
        out = await generate_node(dict(state))
        ms = round((time.perf_counter() - t0) * 1000)
    finally:
        settings.thinking_generation = original
    return {"answer": out.get("generated_answer", ""), "answerable": out.get("answerable"),
            "citations": len(out.get("citations", [])), "latency_ms": ms}


async def _run_hallucination(state: dict, answer: str) -> dict:
    """Tier 2B — cùng config hallucination, chỉ khác câu trả lời đầu vào."""
    t0 = time.perf_counter()
    out = await hallucination_check_node({**state, "generated_answer": answer})
    return {"passed": out.get("hallucination_passed"), "latency_ms": round((time.perf_counter() - t0) * 1000)}


def _pct(v: list[float], p: float) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    k = (len(s) - 1) * p / 100
    f = int(k)
    return s[f] if f + 1 >= len(s) else s[f] + (s[f + 1] - s[f]) * (k - f)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--out", default=str(RESULTS))
    args = parser.parse_args()

    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))["requests"]
    qa = {i["id"]: i for i in json.loads(QA_SET.read_text(encoding="utf-8"))}
    for w in workload:
        src = qa.get(w.get("source") or "")
        if src and src.get("expected_answer"):
            w["expected_keywords"] = re.findall(r"\d+(?:[.,]\d+)?\s*(?:%|ngày|tháng|giờ)", src["expected_answer"])
    items = workload[: args.limit] if args.limit else workload

    print(f"Chuẩn bị generate input (chạy tới hết grade) từ {len(items)} request...", flush=True)
    prepared = await _prepare_inputs(items)
    print(f"-> {len(prepared)} input đi qua generate\n", flush=True)

    rng = random.Random(SEED)
    rows = []
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _flush(partial: bool) -> None:
        """Ghi kết quả sau MỖI cặp.

        Một lần chạy tốn ~12 phút và 4 lệnh gọi LLM cho mỗi cặp; để nó mất trắng
        vì một chớp DNS (đã xảy ra thật) là lãng phí không cần thiết. Ghi dần thì
        lần chạy hỏng vẫn để lại phần đã đo được, và `partial` nói rõ file đang
        dở để không ai đọc nhầm thành kết quả đầy đủ.
        """
        out_path.write_text(
            json.dumps(
                {"run_at": datetime.now(timezone.utc).isoformat(), "partial": partial,
                 "n_done": len(rows), "n_planned": len(prepared), "seed": SEED, "results": rows},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    for n, p in enumerate(prepared, 1):
        # Randomize thứ tự trong cặp: lần gọi thứ hai luôn được hưởng connection
        # warming, nên nếu ON luôn chạy trước thì OFF sẽ được lợi một cách hệ thống.
        on_first = rng.random() < 0.5
        order = ["ON", "OFF"] if on_first else ["OFF", "ON"]
        res = {}
        for side in order:
            res[side] = await _run_generate(p["state"], side == "ON")
            await asyncio.sleep(args.delay)

        chunks = p["state"]["retrieved_chunks"]
        for side in ("ON", "OFF"):
            res[side]["quality"] = _grade_answer(res[side]["answer"], chunks, p["expected_keywords"])
            res[side]["hallucination"] = await _run_hallucination(p["state"], res[side]["answer"])
            await asyncio.sleep(args.delay)

        rows.append({
            "id": p["id"], "category": p["category"], "query": p["query"],
            "order": order, "expected_keywords": p["expected_keywords"],
            "n_chunks": len(chunks),
            # Lưu context để CHẤM LẠI ĐƯỢC OFFLINE khi tiêu chí thay đổi.
            # Bản trước không lưu, nên khi phát hiện regex bắt số sai thì không
            # có cách nào chấm lại ngoài chạy lại toàn bộ API — đúng thứ đã tránh
            # được ở P4A bằng cách giữ nguyên observation và chỉ đổi evaluator.
            "chunk_texts": [c["text"] for c in chunks],
            "ON": res["ON"], "OFF": res["OFF"],
            "paired_delta_ms": res["OFF"]["latency_ms"] - res["ON"]["latency_ms"],
        })
        _flush(partial=True)
        print(
            f"[{n}/{len(prepared)}] {p['id']:<7} order={'/'.join(order):<8} "
            f"ON {res['ON']['latency_ms']:>6}ms / OFF {res['OFF']['latency_ms']:>6}ms "
            f"(Δ {rows[-1]['paired_delta_ms']:+7}ms) · hallu ON={res['ON']['hallucination']['passed']} "
            f"OFF={res['OFF']['hallucination']['passed']}",
            flush=True,
        )

    deltas = [r["paired_delta_ms"] for r in rows]
    summary = {"n": len(rows), "paired_delta_ms": {
        "median": round(_pct(deltas, 50)), "p25": round(_pct(deltas, 25)),
        "p75": round(_pct(deltas, 75)), "mean": round(statistics.mean(deltas)),
        "off_faster_n": sum(1 for d in deltas if d < 0)}}
    for side in ("ON", "OFF"):
        q = [r[side]["quality"] for r in rows]
        summary[side] = {
            "latency_p50_ms": round(_pct([r[side]["latency_ms"] for r in rows], 50)),
            "latency_p95_ms": round(_pct([r[side]["latency_ms"] for r in rows], 95)),
            "all_quality_pass": sum(1 for x in q if all(v for k, v in x.items() if not k.startswith("_"))),
            "per_check": {k: sum(1 for x in q if x[k]) for k in q[0] if not k.startswith("_")},
            "hallucination_pass": sum(1 for r in rows if r[side]["hallucination"]["passed"]),
            "hallucination_latency_p50_ms": round(_pct([r[side]["hallucination"]["latency_ms"] for r in rows], 50)),
            "ungrounded_numbers": sum(len(x["_ungrounded"]) for x in q),
            "sentinel_used": sum(1 for x in q if x["_has_sentinel"]),
        }
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "design": "Tier 2A isolate generate (replay cùng chunks) + Tier 2B downstream hallucination veto. Paired, randomize thứ tự trong cặp.",
        "seed": SEED, "summary": summary, "results": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    d = summary["paired_delta_ms"]
    print(f"\n=== TIER 2A — latency (paired, n={summary['n']}) ===")
    print(f"  median paired delta (OFF-ON) = {d['median']:+}ms   p25={d['p25']:+}ms  p75={d['p75']:+}ms")
    print(f"  OFF nhanh hơn: {d['off_faster_n']}/{summary['n']}")
    print(f"  generate p50: ON {summary['ON']['latency_p50_ms']}ms · OFF {summary['OFF']['latency_p50_ms']}ms")
    print(f"\n=== TIER 2A — quality ===")
    print(f"  {'':<22}{'ON':>8}{'OFF':>8}")
    for k in summary["ON"]["per_check"]:
        print(f"  {k:<22}{summary['ON']['per_check'][k]:>8}{summary['OFF']['per_check'][k]:>8}")
    print(f"  {'all pass':<22}{summary['ON']['all_quality_pass']:>8}{summary['OFF']['all_quality_pass']:>8}")
    print(f"  {'ungrounded numbers':<22}{summary['ON']['ungrounded_numbers']:>8}{summary['OFF']['ungrounded_numbers']:>8}")
    print(f"\n=== TIER 2B — downstream veto ===")
    print(f"  hallucination PASS: ON {summary['ON']['hallucination_pass']}/{summary['n']} · "
          f"OFF {summary['OFF']['hallucination_pass']}/{summary['n']}")
    print(f"  hallucination p50 : ON {summary['ON']['hallucination_latency_p50_ms']}ms · "
          f"OFF {summary['OFF']['hallucination_latency_p50_ms']}ms")
    print(f"\nĐã lưu: {args.out}")


asyncio.run(main())

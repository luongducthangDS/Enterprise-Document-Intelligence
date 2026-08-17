#!/usr/bin/env python3
"""A/B `thinking_condense` ON vs OFF — hai tầng, xem eval/CONDENSE_EVAL_SPEC.md.

Tầng 1 (mô tả): chất lượng rewrite + latency riêng của condense_node.
Tầng 2 (quyết định): hệ quả downstream — retrieval có kéo đúng nguồn không,
câu trả lời cuối có đúng không, có escalate/hỏi lại oan không, E2E latency.

Kỷ luật A/B: cùng history, cùng query, cùng corpus/retrieval/generation config;
biến số duy nhất là enable_thinking của condense. Case nào ON/OFF cho retrieval
GIỐNG nhau mà đáp án khác nhau được đánh dấu `generation_variance`, không tính
là condense regression.

Chạy: python eval/scripts/eval_condense_thinking.py [--limit N] [--out FILE]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.graph import agent  # noqa: E402
from src.config import get_settings  # noqa: E402

DATASET = "eval/datasets/condense_multiturn_set.json"
RESULTS = "eval/results/condense_thinking_ab.json"
DELAY_S = float(os.environ.get("AB_DELAY", "1.0"))
# Ngưỡng để một chunk được coi là EVIDENCE ĐÁNG KỂ khi so hai nhánh.
#
# Không dùng "top-K chunk đầu" làm định nghĩa: generate_node đưa TOÀN BỘ
# retrieved_chunks vào prompt, nên số lượng chunk không phải thứ quyết định —
# thứ quyết định là chunk đó có đủ liên quan để đổi được câu trả lời hay không.
# Neo theo phân phối rerank score đã đo (xem `rerank_min_score` trong
# src/config.py): câu in_scope có top-1 median 0.975 / p10 0.490, còn
# out_of_scope median 0.010. Chunk dưới 0.5 nằm ở vùng "được giữ lại nhưng
# không phải nguồn trả lời".
MATERIAL_EVIDENCE_SCORE = 0.5


def _set_thinking(enabled: bool) -> None:
    """Đổi cờ trên settings đã cache — cả condense_node lẫn graph đều đọc từ đây."""
    get_settings().thinking_condense = enabled


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _classify_failure(item: dict, rewrite: str) -> str | None:
    """Ba failure mode trong spec, chấm bằng tín hiệu xác định — không LLM judge."""
    low = _norm(rewrite)
    if item["must_keep"] and not any(_norm(k) in low for k in item["must_keep"]):
        # Nhóm topic_switch không được kéo chủ đề cũ; mất must_keep ở đó nghĩa là
        # rewrite lạc hẳn sang chuyện khác, vẫn tính là mất tham chiếu.
        return "reference_loss"
    for bad in item["must_not_contain"]:
        if _norm(bad) in low:
            return "topic_contamination" if item["category"] == "topic_switch" else "reference_misresolution"
    return None


async def _retry(coro_factory, attempts: int = 4):
    for attempt in range(attempts):
        try:
            return await coro_factory()
        except Exception:  # noqa: BLE001 — 429/5xx thoáng qua của gateway
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(3 * (attempt + 1))


async def _stream_once(state: dict) -> tuple[dict, int, int]:
    """Chạy graph MỘT lần, lấy cả rewrite, latency riêng của condense và E2E.

    Cố ý không gọi condense_node tách rời rồi chạy graph lần nữa: làm vậy là
    chạy condense hai lần cho mỗi side, tốn gấp đôi API và nhét thêm nhiễu
    gateway vào chính con số E2E đang cần đo.
    """
    final: dict = dict(state)
    started = time.perf_counter()
    condense_ms = 0
    async for step in agent.astream(dict(state), stream_mode="updates"):
        for node_name, delta in step.items():
            if node_name == "condense":
                condense_ms = round((time.perf_counter() - started) * 1000)
            final.update(delta)
    return final, condense_ms, round((time.perf_counter() - started) * 1000)


async def _run_side(item: dict, thinking: bool) -> dict:
    _set_thinking(thinking)
    state = {"query": item["query"], "history": item["history"]}

    final, condense_ms, e2e_ms = await _retry(lambda: _stream_once(state))
    rewrite = final.get("condensed_query", "")

    chunks = final.get("retrieved_chunks", []) or []
    retrieved_ids = [c["chunk_id"] for c in chunks]
    retrieved_scored = [{"chunk_id": c["chunk_id"], "score": c.get("score")} for c in chunks]
    sources = {c.get("source_file", "").lower() for c in chunks}
    response = final.get("response", "")

    retrieval_hit = any(
        any(want.lower() in src for src in sources) for want in item["expected_source_contains"]
    )
    kws = item["expected_answer_keywords"]
    answer_correct = (not kws) or any(str(k).lower() in response.lower() for k in kws)

    return {
        "rewrite": rewrite,
        "condense_latency_ms": condense_ms,
        "e2e_latency_ms": e2e_ms,
        "retrieved_ids": retrieved_ids,
        "retrieved_scored": retrieved_scored,
        "top_score": chunks[0].get("score") if chunks else None,
        "retrieval_hit": retrieval_hit,
        "answerable": final.get("answerable"),
        "final_correct": bool(retrieval_hit and answer_correct and not final.get("escalate", False)),
        "escalated": bool(final.get("escalate", False)),
        "needs_clarification": bool(final.get("needs_clarification", False)),
        "confidence_score": final.get("confidence_score"),
        "response": response[:400],
        "failure_mode": _classify_failure(item, rewrite),
    }


def _same_effective_context(on: dict, off: dict) -> bool:
    """Hai nhánh có cùng phần context thực sự chi phối câu trả lời hay không.

    Định nghĩa: cùng tập EVIDENCE ĐÁNG KỂ (score >= MATERIAL_EVIDENCE_SCORE),
    và phần chênh lệch giữa hai bên không có evidence đáng kể nào mới.

    Vì sao không so cả danh sách chunk: đo thực tế (cd_008) cho thấy hai nhánh
    có thể ra cùng các chunk chi phối theo đúng thứ tự, chỉ khác một chunk đuôi
    score thấp. So bằng `==` trên cả list thì case rơi nhầm vào nhóm "condense
    gây regression" — tức đổ cho condense một lỗi thực ra sinh ở tầng
    generate/hallucination.

    Vì sao cũng không dùng "top-K chunk đầu": K là con số tuỳ tiện, và
    generate_node vốn đưa toàn bộ chunk vào prompt. Điều đáng hỏi không phải
    "có bao nhiêu chunk giống nhau" mà "phần khác nhau có đủ sức đổi câu trả
    lời không".
    """

    def material(side: dict) -> set[str]:
        return {
            c["chunk_id"]
            for c in side.get("retrieved_scored", [])
            if c.get("score") is not None and c["score"] >= MATERIAL_EVIDENCE_SCORE
        }

    return material(on) == material(off)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = int(k)
    return s[f] if f + 1 >= len(s) else s[f] + (s[f + 1] - s[f]) * (k - f)


def _summarize(rows: list[dict], side: str) -> dict:
    n = len(rows)
    r = [x[side] for x in rows]
    crit = [x[side] for x in rows if x["critical"]]
    return {
        "n": n,
        "retrieval_hit": sum(1 for x in r if x["retrieval_hit"]),
        "final_correct": sum(1 for x in r if x["final_correct"]),
        "escalated": sum(1 for x in r if x["escalated"]),
        "escalated_critical": sum(1 for x in crit if x["escalated"]),
        "needs_clarification": sum(1 for x in r if x["needs_clarification"]),
        "failures": {
            mode: sum(1 for x in r if x["failure_mode"] == mode)
            for mode in ("reference_loss", "reference_misresolution", "topic_contamination")
        },
        "condense_p50_ms": round(_pct([x["condense_latency_ms"] for x in r], 50)),
        "condense_p95_ms": round(_pct([x["condense_latency_ms"] for x in r], 95)),
        "e2e_p50_ms": round(_pct([x["e2e_latency_ms"] for x in r], 50)),
        "e2e_p95_ms": round(_pct([x["e2e_latency_ms"] for x in r], 95)),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=RESULTS)
    args = parser.parse_args()

    with open(DATASET, encoding="utf-8") as f:
        items = json.load(f)
    if args.limit:
        items = items[: args.limit]
    print(f"{len(items)} case · biến số: thinking_condense ON/OFF", flush=True)

    rows = []
    for n, item in enumerate(items, 1):
        on = await _run_side(item, True)
        await asyncio.sleep(DELAY_S)
        off = await _run_side(item, False)
        await asyncio.sleep(DELAY_S)

        variance = _same_effective_context(on, off) and on["final_correct"] != off["final_correct"]
        rows.append(
            {
                "id": item["id"],
                "category": item["category"],
                "critical": item["critical"],
                "history": item["history"],
                "query": item["query"],
                "generation_variance": variance,
                "thinking_on": on,
                "thinking_off": off,
            }
        )
        flag = " [generation_variance]" if variance else ""
        print(
            f"[{n}/{len(items)}] {item['id']} {item['category']:<19} "
            f"ON correct={on['final_correct']} / OFF correct={off['final_correct']}"
            f" | OFF failure={off['failure_mode']}{flag}",
            flush=True,
        )

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "spec": "eval/CONDENSE_EVAL_SPEC.md",
        "dataset": DATASET,
        "thinking_on": _summarize(rows, "thinking_on"),
        "thinking_off": _summarize(rows, "thinking_off"),
        "generation_variance_cases": [r["id"] for r in rows if r["generation_variance"]],
        "results": rows,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    on, off = report["thinking_on"], report["thinking_off"]
    print(f"\n{'Metric':<28}{'thinking ON':>14}{'thinking OFF':>15}")
    print("-" * 57)
    for key, label in [
        ("final_correct", "Answer correct"),
        ("retrieval_hit", "Retrieval hit"),
        ("escalated", "Escalated"),
        ("escalated_critical", "Escalated (critical)"),
        ("needs_clarification", "Clarification"),
        ("condense_p50_ms", "Condense p50 (ms)"),
        ("condense_p95_ms", "Condense p95 (ms)"),
        ("e2e_p50_ms", "E2E p50 (ms)"),
        ("e2e_p95_ms", "E2E p95 (ms)"),
    ]:
        print(f"{label:<28}{on[key]:>14}{off[key]:>15}")
    print(f"\nFailure mode (OFF): {json.dumps(off['failures'], ensure_ascii=False)}")
    print(f"Failure mode (ON) : {json.dumps(on['failures'], ensure_ascii=False)}")
    print(f"generation_variance: {report['generation_variance_cases']}")
    print(f"\nĐã lưu: {args.out}")


asyncio.run(main())

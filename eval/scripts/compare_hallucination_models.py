#!/usr/bin/env python3
"""So sánh model ứng viên với model hiện tại cho hallucination_check_node —
REPLAY OFFLINE từ agent_eval_report.json, KHÔNG chạy lại agent.

Tại sao replay được: report đã lưu full `response` + `retrieved_chunk_ids` của
từng câu — chỉ cần lấy lại text chunk từ Chroma Cloud rồi gọi đúng
_HALLUCINATION_SYSTEM prompt với từng model, so verdict PASS/FAIL giữa 2 model
(agreement) + latency. Rẻ hơn nhiều so với chạy lại agent (1 call/câu/model
thay vì 3-8 call/câu) và loại bỏ nhiễu từ các node khác.

Điều kiện đổi default `hallucination_model` trong config: agreement >= 95%
với model hiện tại (GLM-5.2) và nhanh hơn rõ rệt.

Chạy: python eval/scripts/compare_hallucination_models.py --candidate DeepSeek-V4-Flash
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

from src.agents.llm import acall_llm  # noqa: E402
from src.agents.nodes.generation import _HALLUCINATION_SYSTEM  # noqa: E402
from src.agents.nodes.retrieval import _collection  # noqa: E402
from src.config import get_settings  # noqa: E402

REPORT_PATH = "eval/results/agent_eval_report.json"
RESULTS_PATH = "eval/results/hallucination_model_ab.json"


def _load_replay_items(limit: int | None) -> list[dict]:
    with open(REPORT_PATH, encoding="utf-8") as f:
        report = json.load(f)
    items = [
        r for r in report["results"]
        if r["type"] == "in_scope" and r.get("response") and r.get("retrieved_chunk_ids")
    ]
    if limit:
        items = items[:limit]
    return items


def _fetch_chunk_texts(items: list[dict]) -> dict[str, str]:
    """Lấy text của toàn bộ chunk_id xuất hiện trong replay set — 1 lần gọi
    Chroma cho tất cả, không gọi lẻ từng câu."""
    all_ids = sorted({cid for r in items for cid in r["retrieved_chunk_ids"]})
    result = _collection().get(ids=all_ids, include=["documents"])
    return dict(zip(result.get("ids") or [], result.get("documents") or []))


def _build_context(chunk_ids: list[str], texts: dict[str, str]) -> str:
    parts = [f"[Nguồn {i}] {texts[cid]}" for i, cid in enumerate(chunk_ids, start=1) if cid in texts]
    return "\n\n".join(parts) if parts else "(không tìm thấy đoạn trích liên quan)"


async def _verdict(model: str, context: str, answer: str, semaphore: asyncio.Semaphore) -> tuple[bool, float]:
    user_prompt = f"Đoạn trích:\n{context}\n\nCâu trả lời cần kiểm tra:\n{answer}"
    async with semaphore:
        t0 = time.perf_counter()
        raw = await acall_llm(_HALLUCINATION_SYSTEM, user_prompt, temperature=0.0, model=model)
        latency_ms = (time.perf_counter() - t0) * 1000
    return "PASS" in raw.upper(), latency_ms


async def _run_one(
    item: dict, texts: dict[str, str], baseline_model: str, candidate_model: str, semaphore: asyncio.Semaphore
) -> dict:
    context = _build_context(item["retrieved_chunk_ids"], texts)
    answer = item["response"]
    try:
        # Tuần tự trong 1 câu (baseline rồi candidate) — song song giữa các câu
        # đã có semaphore lo; không nhân đôi áp lực lên gateway cùng lúc.
        base_pass, base_ms = await _verdict(baseline_model, context, answer, semaphore)
        cand_pass, cand_ms = await _verdict(candidate_model, context, answer, semaphore)
    except Exception as e:  # noqa: BLE001 — lỗi mạng 1 câu không được chết cả batch
        return {"id": item["id"], "error": str(e)}
    return {
        "id": item["id"],
        "baseline_pass": base_pass,
        "candidate_pass": cand_pass,
        "agree": base_pass == cand_pass,
        "baseline_ms": round(base_ms, 1),
        "candidate_ms": round(cand_ms, 1),
    }


def _p50(values: list[float]) -> float:
    return sorted(values)[len(values) // 2] if values else 0.0


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, help="Model ứng viên (vd DeepSeek-V4-Flash)")
    parser.add_argument("--limit", type=int, default=None, help="Chỉ replay N câu đầu")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--out", default=RESULTS_PATH)
    args = parser.parse_args()

    settings = get_settings()
    baseline_model = settings.hallucination_model or settings.llm_model

    items = _load_replay_items(args.limit)
    print(f"Replay {len(items)} câu — baseline: {baseline_model} vs candidate: {args.candidate}")
    texts = _fetch_chunk_texts(items)
    print(f"Đã tải {len(texts)} chunk text từ Chroma")

    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    done = 0
    for coro in asyncio.as_completed(
        [_run_one(it, texts, baseline_model, args.candidate, semaphore) for it in items]
    ):
        r = await coro
        results.append(r)
        done += 1
        if r.get("error"):
            print(f"[{done}/{len(items)}] {r['id']} LỖI: {r['error'][:80]}")
        else:
            mark = "=" if r["agree"] else "≠"
            print(
                f"[{done}/{len(items)}] {r['id']} base={'PASS' if r['baseline_pass'] else 'FAIL'} "
                f"{mark} cand={'PASS' if r['candidate_pass'] else 'FAIL'} "
                f"({r['baseline_ms']:.0f}ms vs {r['candidate_ms']:.0f}ms)"
            )

    results.sort(key=lambda r: r["id"])
    ok = [r for r in results if not r.get("error")]
    agree = sum(1 for r in ok if r["agree"])
    agreement = agree / len(ok) if ok else 0.0
    base_p50 = _p50([r["baseline_ms"] for r in ok])
    cand_p50 = _p50([r["candidate_ms"] for r in ok])

    print(f"\n=== Agreement: {agree}/{len(ok)} ({agreement:.1%}) — ngưỡng đổi model: >= 95% ===")
    print(f"Latency p50: baseline {base_p50:.0f}ms vs candidate {cand_p50:.0f}ms")
    disagreements = [r["id"] for r in ok if not r["agree"]]
    if disagreements:
        print(f"Câu bất đồng: {disagreements}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_at": datetime.now(timezone.utc).isoformat(),
                "baseline_model": baseline_model,
                "candidate_model": args.candidate,
                "n": len(ok),
                "n_errors": len(results) - len(ok),
                "agreement": round(agreement, 3),
                "baseline_p50_ms": round(base_p50, 1),
                "candidate_p50_ms": round(cand_p50, 1),
                "disagreements": disagreements,
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Đã lưu: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

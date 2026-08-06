#!/usr/bin/env python3
"""Chạy toàn bộ eval/datasets/qa_eval_set.json (100 câu) qua agent RAG thật
(src/agents/graph.py) và chấm điểm hành vi theo đúng type/expected_behavior:

- in_scope (60 câu): PASS khi cả 3 điều kiện đúng —
  (1) có response, (2) retrieved_chunks chứa ground_truth_context (retrieval
  đúng), (3) LLM-judge xác nhận response khớp nội dung cốt lõi với
  expected_answer (generation đúng). Trước đây chỉ check (1)+(2) — response
  có thể sai hoàn toàn vẫn PASS nếu retrieve đúng chunk (xem CLAUDE.md
  [2026-08-06], review glm_review.md mục 2.1).
- ambiguous (15 câu): agent phải trả về needs_clarification=True.
- out_of_scope (15 câu): agent phải escalate=True (tạo ticket — có dữ liệu
  cá nhân/vấn đề thật để HR xử lý).
- competitor_comparison (10 câu): agent phải TỪ CHỐI LỊCH SỰ, KHÔNG tạo ticket
  (escalate=False, escalate_reason="competitor_question") — trước đây chấm
  chung với out_of_scope (escalate=True), sai vì không có gì để HR công ty
  mình xử lý khi hỏi chính sách công ty khác (xem CLAUDE.md [2026-08-06],
  review glm_review.md mục 3.5).

Đo thêm latency (p50/p95) mỗi lần agent.ainvoke() — review glm_review.md mục
3.2 chỉ ra trước đó không có số liệu hiệu năng nào.

Chạy: python eval/scripts/eval_agent.py [--limit N] [--concurrency N]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from _text_utils import normalize_for_match  # noqa: E402
from src.agents.graph import agent  # noqa: E402
from _stats import bootstrap_ci, format_ci  # noqa: E402
from src.agents.llm import acall_llm  # noqa: E402
from src.config import get_settings  # noqa: E402

EVAL_SET_PATH = "eval/datasets/qa_eval_set.json"
RESULTS_PATH = "eval/results/agent_eval_report.json"
QRELS_PATH = "eval/datasets/retrieval_qrels.json"

_JUDGE_SYSTEM = """Bạn là giám khảo chấm câu trả lời của chatbot HR nội bộ. So sánh CÂU TRẢ LỜI THỰC TẾ của agent với CÂU TRẢ LỜI MẪU — chỉ quan tâm nội dung/thông tin cốt lõi (số liệu, điều kiện, quy trình) có khớp không, KHÔNG cần giống hệt câu chữ (agent có thể diễn đạt khác, có thêm chi tiết phụ, hoặc trích dẫn nguồn). Trả lời ĐÚNG 1 từ: "CORRECT" nếu câu trả lời thực tế truyền tải đúng thông tin cốt lõi của câu trả lời mẫu, "INCORRECT" nếu thiếu/sai thông tin cốt lõi hoặc mâu thuẫn với câu trả lời mẫu."""


def _context_found(item: dict, chunks: list[dict], qrels: dict) -> bool:
    """Retrieval có lấy được đoạn chứa câu trả lời không.

    Ưu tiên so `chunk_id` với qrel (chính xác, không phụ thuộc ranh giới
    chunking); chỉ khi câu đó chưa có qrel mới lùi về so chuỗi. So chuỗi đơn
    thuần từng cho kết quả sai hệ thống khi `ground_truth_context` (median
    2.000 ký tự) dài hơn cả `chunk_max_chars` (1.500) — khi đó không chunk nào
    chứa nổi nó nên luôn báo False dù retrieval hoàn toàn đúng.
    """
    relevant_ids = set(qrels.get(item.get("id"), {}))
    if not relevant_ids and item.get("evidence_chunk_id"):
        relevant_ids = {item["evidence_chunk_id"]}
    if relevant_ids:
        return any(chunk.get("chunk_id") in relevant_ids for chunk in chunks)

    needle = normalize_for_match(item.get("ground_truth_context", ""))
    if not needle:
        return False
    return any(needle in normalize_for_match(chunk.get("text", "")) for chunk in chunks)


def _parse_verdict(text: str) -> bool:
    text = text.strip().upper()
    if "INCORRECT" in text:
        return False
    return "CORRECT" in text


async def _judge_answer(question: str, response: str, expected_answer: str) -> bool:
    if not expected_answer or not response:
        return False
    user = f"Câu hỏi: {question}\n\nCâu trả lời mẫu: {expected_answer}\n\nCâu trả lời thực tế của agent: {response}"
    # Judge PHẢI khác model với agent: cùng model vừa trả lời vừa tự chấm thì
    # điểm phản ánh độ nhất quán của model với chính nó (circular evaluation).
    verdict = await acall_llm(_JUDGE_SYSTEM, user, temperature=0.0, model=get_settings().judge_model)
    return _parse_verdict(verdict)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = min(len(sorted_vals) - 1, round(p / 100 * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


async def _run_one(item: dict, semaphore: asyncio.Semaphore, qrels: dict) -> dict:
    """Toàn bộ thân hàm (agent.ainvoke + judge call) bọc trong 1 try/except —
    lỗi mạng thoáng qua ở BẤT KỲ bước nào (kể cả judge, gọi LLM lần 2) không
    được để crash cả batch, chỉ ghi nhận lỗi cho đúng 1 câu (đã xảy ra thật:
    FPT.AI trả 524 ở judge call của câu 99/100, làm mất 99 kết quả đã chạy
    xong vì file chỉ ghi ở cuối main() — xem CLAUDE.md [2026-08-06])."""
    item_type = item["type"]
    async with semaphore:
        t0 = time.perf_counter()
        try:
            result = await agent.ainvoke({"query": item["question"]})
            latency_ms = (time.perf_counter() - t0) * 1000

            extra: dict = {}
            if item_type == "in_scope":
                chunks = result.get("retrieved_chunks", [])
                context_found = _context_found(item, chunks, qrels)
                answer_correct = await _judge_answer(
                    item["question"], result.get("response", ""), item.get("expected_answer", "")
                )
                passed = bool(result.get("response")) and context_found and answer_correct
                extra = {"context_found": context_found, "answer_correct": answer_correct}
            elif item_type == "ambiguous":
                passed = result.get("needs_clarification") is True
            elif item_type == "competitor_comparison":
                passed = result.get("escalate") is False and result.get("escalate_reason") == "competitor_question"
            else:  # out_of_scope
                passed = result.get("escalate") is True
        except Exception as e:  # noqa: BLE001 — muốn ghi nhận lỗi thay vì crash cả batch
            return {
                "id": item["id"], "type": item_type, "category": item["category"],
                "error": str(e), "passed": False, "latency_ms": None,
            }

    return {
        "id": item["id"],
        "type": item_type,
        "category": item["category"],
        "question": item["question"],
        "passed": passed,
        "intent": result.get("intent"),
        "escalate": result.get("escalate", False),
        "escalate_reason": result.get("escalate_reason"),
        "needs_clarification": result.get("needs_clarification", False),
        "confidence_score": result.get("confidence_score"),
        "num_retrieved_chunks": len(result.get("retrieved_chunks", [])),
        "response_preview": (result.get("response") or "")[:200],
        # Lưu câu trả lời ĐẦY ĐỦ: đổi judge hoặc đổi tiêu chí chấm sau này chỉ
        # cần chấm lại offline, không phải chạy lại toàn bộ agent (~20 phút +
        # API). Đã mất công chạy lại 1 lần vì chỉ lưu 200 ký tự đầu.
        "response": result.get("response") or "",
        "retrieved_chunk_ids": [c.get("chunk_id") for c in result.get("retrieved_chunks", [])],
        "retrieved_scores": [c.get("score") for c in result.get("retrieved_chunks", [])],
        "latency_ms": round(latency_ms, 1),
        **extra,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Chỉ chạy N câu đầu (debug nhanh)")
    parser.add_argument("--concurrency", type=int, default=3, help="Số câu chạy song song")
    parser.add_argument(
        "--types", nargs="*", default=None,
        help="Chỉ chạy các type này (vd in_scope). Dùng khi A/B một thay đổi chỉ ảnh hưởng 1 nhánh — "
             "chạy đúng tập bị ảnh hưởng thì so được theo cặp và rẻ hơn nhiều",
    )
    parser.add_argument("--out", default=RESULTS_PATH, help="Đường dẫn file báo cáo")
    parser.add_argument(
        "--dataset", default=EVAL_SET_PATH,
        help="Bộ câu hỏi (mặc định qa_eval_set.json — dev set đã dùng để tune). "
             "Dùng eval/datasets/qa_heldout_set.json để đo số held-out sạch.",
    )
    parser.add_argument(
        "--qrels", default=QRELS_PATH,
        help="Qrel chunk-level tương ứng --dataset. Không bắt buộc: qa_heldout_set.json đã "
             "có sẵn evidence_chunk_id nên _context_found tự lùi về đó nếu file này không tồn tại.",
    )
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        items = json.load(f)
    if args.types:
        items = [it for it in items if it["type"] in args.types]
        print(f"[types={','.join(args.types)}] {len(items)} câu")
    if args.limit:
        items = items[: args.limit]

    qrels: dict = {}
    if os.path.exists(args.qrels):
        with open(args.qrels, encoding="utf-8") as f:
            qrels = json.load(f)
    else:
        print(f"[CẢNH BÁO] không có {args.qrels} — context_found sẽ lùi về evidence_chunk_id/so chuỗi")

    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    done = 0
    for coro in asyncio.as_completed([_run_one(item, semaphore, qrels) for item in items]):
        r = await coro
        results.append(r)
        done += 1
        status = "OK" if r["passed"] else "FAIL"
        print(f"[{done}/{len(items)}] {status} {r['id']} ({r['type']}/{r['category']})")

    results.sort(key=lambda r: r["id"])

    by_type: dict[str, list[dict]] = {}
    for r in results:
        by_type.setdefault(r["type"], []).append(r)

    print()
    print("=== Kết quả theo type ===")
    summary = {}
    for t, rs in sorted(by_type.items()):
        passed = sum(1 for r in rs if r["passed"])
        rate = passed / len(rs) if rs else 0.0
        point, lo, hi = bootstrap_ci([1.0 if r["passed"] else 0.0 for r in rs])
        summary[t] = {"passed": passed, "total": len(rs), "rate": round(rate, 3), "ci": [round(lo, 3), round(hi, 3)]}
        print(f"{t}: {passed}/{len(rs)} — {format_ci(point, lo, hi)}")

    total_passed = sum(1 for r in results if r["passed"])
    tp, tlo, thi = bootstrap_ci([1.0 if r["passed"] else 0.0 for r in results])
    summary["total_ci"] = [round(tlo, 3), round(thi, 3)]
    print(f"\nTổng: {total_passed}/{len(results)} — {format_ci(tp, tlo, thi)}")
    print(f"(judge: {get_settings().judge_model} | agent: {get_settings().llm_model})")

    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    if latencies:
        p50, p95 = _percentile(latencies, 50), _percentile(latencies, 95)
        summary["latency_p50_ms"] = round(p50, 1)
        summary["latency_p95_ms"] = round(p95, 1)
        print(f"\n=== Latency (n={len(latencies)}) ===")
        print(f"p50: {p50:.0f}ms, p95: {p95:.0f}ms, max: {max(latencies):.0f}ms")
        for t, rs in sorted(by_type.items()):
            t_latencies = [r["latency_ms"] for r in rs if r.get("latency_ms") is not None]
            if t_latencies:
                summary[f"latency_p50_ms_{t}"] = round(_percentile(t_latencies, 50), 1)
                print(f"  {t}: p50={_percentile(t_latencies, 50):.0f}ms")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "dataset": args.dataset,
        "total": len(results),
        "total_passed": total_passed,
        "summary_by_type": summary,
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nĐã lưu chi tiết: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

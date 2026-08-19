"""Chấm điểm 1 lượt eval agent — dùng chung cho evaluation worker.

Quy tắc chấm giữ đúng như eval/scripts/eval_agent.py (bộ eval đang dùng để ra
số trong docs), chỉ khác là ở đây chúng nằm trong src/ để chạy được bên trong
container agent:

- in_scope: PASS khi có response, retrieval lấy được đoạn chứa câu trả lời, VÀ
  LLM-judge xác nhận nội dung cốt lõi khớp expected_answer.
- ambiguous: PASS khi agent hỏi lại (needs_clarification=True).
- out_of_scope: PASS khi agent escalate (tạo ticket cho HR).
- competitor_comparison: PASS khi agent từ chối lịch sự mà KHÔNG tạo ticket.
"""

from __future__ import annotations

from typing import Any

from src.agents.llm import acall_llm
from src.config import Settings
from src.evaluation.text import normalize_for_match

JUDGE_SYSTEM = """Bạn là giám khảo chấm câu trả lời của chatbot HR nội bộ. So sánh CÂU TRẢ LỜI THỰC TẾ của agent với CÂU TRẢ LỜI MẪU — chỉ quan tâm nội dung/thông tin cốt lõi (số liệu, điều kiện, quy trình) có khớp không, KHÔNG cần giống hệt câu chữ (agent có thể diễn đạt khác, có thêm chi tiết phụ, hoặc trích dẫn nguồn). Trả lời ĐÚNG 1 từ: "CORRECT" nếu câu trả lời thực tế truyền tải đúng thông tin cốt lõi của câu trả lời mẫu, "INCORRECT" nếu thiếu/sai thông tin cốt lõi hoặc mâu thuẫn với câu trả lời mẫu."""


def relevant_chunk_ids(item: dict, qrels: dict) -> set[str]:
    ids = set(qrels.get(item.get("id"), {}))
    if not ids and item.get("evidence_chunk_id"):
        ids = {item["evidence_chunk_id"]}
    return ids


def context_found(item: dict, chunks: list[dict], qrels: dict) -> bool:
    """Retrieval có lấy được đoạn chứa câu trả lời không.

    Ưu tiên so `chunk_id` với qrel (chính xác, không phụ thuộc ranh giới
    chunking); chỉ khi câu đó chưa có qrel mới lùi về so chuỗi — `ground_truth_context`
    (median ~2.000 ký tự) thường dài hơn `chunk_max_chars` nên so chuỗi đơn thuần
    báo MISS oan.
    """
    ids = relevant_chunk_ids(item, qrels)
    if ids:
        return any(chunk.get("chunk_id") in ids for chunk in chunks)

    needle = normalize_for_match(item.get("ground_truth_context", ""))
    if not needle:
        return False
    return any(needle in normalize_for_match(chunk.get("text", "")) for chunk in chunks)


def parse_verdict(text: str) -> bool:
    text = text.strip().upper()
    if "INCORRECT" in text:
        return False
    return "CORRECT" in text


async def judge_answer(question: str, response: str, expected_answer: str, settings: Settings) -> bool:
    if not expected_answer or not response:
        return False
    user = f"Câu hỏi: {question}\n\nCâu trả lời mẫu: {expected_answer}\n\nCâu trả lời thực tế của agent: {response}"
    # Judge PHẢI khác model với agent: cùng model vừa trả lời vừa tự chấm thì
    # điểm phản ánh độ nhất quán của model với chính nó (circular evaluation).
    verdict = await acall_llm(JUDGE_SYSTEM, user, temperature=0.0, model=settings.judge_model)
    return parse_verdict(verdict)


def citation_scores(item: dict, citations: list[dict], qrels: dict) -> tuple[bool, float | None]:
    """(có trích dẫn không, tỉ lệ trích dẫn trỏ đúng đoạn gold).

    Tỉ lệ đúng chỉ tính được khi câu hỏi có nhãn gold (qrel hoặc
    evidence_chunk_id) — không có nhãn thì trả None để không làm loãng mẫu số.
    """
    has_citation = bool(citations)
    ids = relevant_chunk_ids(item, qrels)
    if not ids or not citations:
        return has_citation, None
    hits = sum(1 for c in citations if c.get("chunk_id") in ids)
    return has_citation, hits / len(citations)


def passed_for_type(item_type: str, result: dict[str, Any], *, context_ok: bool, answer_ok: bool) -> bool:
    if item_type == "in_scope":
        return bool(result.get("response")) and context_ok and answer_ok
    if item_type == "ambiguous":
        return result.get("needs_clarification") is True
    if item_type == "pure_statutory":
        return result.get("intent") == "pure_statutory" and (
            result.get("state") == "OUT_OF_SCOPE" or result.get("reason_code") == "PURE_STATUTORY"
        )
    if item_type == "competitor_comparison":
        return result.get("escalate") is False and result.get("escalate_reason") == "competitor_question"
    return result.get("escalate") is True  # out_of_scope


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = min(len(sorted_vals) - 1, round(p / 100 * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def aggregate_metrics(results: list[dict], retrieval_k: int) -> dict[str, Any]:
    in_scope = [r for r in results if r["type"] == "in_scope" and not r.get("error")]
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    citation_rates = [r["citation_correctness"] for r in in_scope if r.get("citation_correctness") is not None]

    return {
        "retrieval_k": retrieval_k,
        "recall_at_k": _mean([1.0 if r.get("context_found") else 0.0 for r in in_scope]),
        "answer_correctness": _mean([1.0 if r.get("answer_correct") else 0.0 for r in in_scope]),
        "citation_coverage": _mean([1.0 if r.get("has_citation") else 0.0 for r in in_scope]),
        "citation_correctness": _mean(citation_rates),
        "p50_latency_ms": round(percentile(latencies, 50), 1) if latencies else None,
        "p95_latency_ms": round(percentile(latencies, 95), 1) if latencies else None,
    }


def evaluate_quality_gate(metrics: dict[str, Any], settings: Settings) -> tuple[str, list[dict]]:
    """PASSED khi mọi ngưỡng đạt; thiếu số liệu (None) thì gate = PENDING."""
    checks = [
        ("recall_at_k", metrics.get("recall_at_k"), settings.eval_gate_recall_at_k),
        ("answer_correctness", metrics.get("answer_correctness"), settings.eval_gate_answer_correctness),
        ("citation_coverage", metrics.get("citation_coverage"), settings.eval_gate_citation_coverage),
    ]
    details = [
        {"metric": name, "value": value, "threshold": threshold, "passed": None if value is None else value >= threshold}
        for name, value, threshold in checks
    ]

    if any(d["passed"] is None for d in details):
        return "PENDING", details
    return ("PASSED" if all(d["passed"] for d in details) else "FAILED"), details

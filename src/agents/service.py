"""Điểm vào duy nhất mà lớp bên ngoài (API, backend team, script debug) cần
biết để gọi agent — bọc `agent.ainvoke()` và dịch `AgentState` (TypedDict nội
bộ, có field runtime-only như `rewrite_count`/`hallucination_retry_count`)
sang `AgentAnswer` (Pydantic, contract ổn định — xem docs/AGENT_API.md).

Trước bản này, src/api/routes.py tự đọc `result.get("response")` trực tiếp từ
AgentState và vứt bỏ toàn bộ citations/confidence/escalate/ticket draft ngay
tại lớp gọi — backend không có cách nào lấy lại các trường đó mà không tự đọc
state nội bộ của agent.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from src.agents.graph import agent
from src.agents.guardrails import redact_pii
from src.agents.state import AgentState
from src.config import get_settings
from src.models.schemas import AgentAnswer, BoundaryDecisionDTO, Citation, TicketDraft
from src.observability import llm_trace

_RETRIEVE_TOOL_NAME = "hr_policy_search"
# ~15 từ/chunk (tiếng Việt trung bình 4-6 ký tự/từ) -> chunk vừa đủ nhỏ để tạo
# hiệu ứng gõ chữ mượt, vừa đủ lớn để không spam quá nhiều event/response ngắn.
_ANSWER_CHUNK_WORDS = 15

# Tri-state contract (NexaTech Type-C contract v3.1.0, frozen) — map escalate_reason
# (lịch sử, 6 giá trị, vẫn giữ nguyên cho ticket routing/backward-compat) sang
# reason_code (contract, chỉ 2 giá trị cho ABSTAIN). competitor_question/
# human_first_required có escalate=False (không tạo ticket) nhưng VẪN LÀ một
# lượt từ chối — phải map dù không tạo ticket, nên tra theo escalate_reason,
# KHÔNG theo escalate.
_ABSTAIN_REASON_CODE: dict[str, str] = {
    "personal_data_required": "requires_live_personal_data",
    "user_requested_human": "requires_live_personal_data",
    "human_first_required": "requires_live_personal_data",
    "low_confidence": "missing_policy_evidence",
    "out_of_scope": "missing_policy_evidence",
    "competitor_question": "missing_policy_evidence",
    "department_scope_denied": "missing_policy_evidence",
    # Không có câu trả lời bám nguồn sau khi hết lượt sinh lại -> thiếu bằng chứng.
    "hallucination_detected": "missing_policy_evidence",
    "requires_live_accounting_erp_data": "requires_live_personal_data",
}

def _derive_runtime_state(state: AgentState) -> tuple[str, str | None]:
    """Tính tập trung MỘT LẦN, không để từng node tự set — tránh một nhánh quên
    gán rồi rơi về None âm thầm. Thứ tự kiểm tra phản ánh routing_precedence:

    1. intent=pure_statutory (routing precedence priority 2) -> OUT_OF_SCOPE,
       bất kể escalate_reason (out_of_scope_node không tạo ticket nên
       escalate_reason luôn rỗng ở nhánh này, nhưng intent là tín hiệu đáng
       tin cậy hơn vì được set ngay tại router, không phụ thuộc node nào chạy
       sau).
    2. escalate_reason có mặt (dù escalate=True hay False — competitor/
       human_first vẫn là một lượt từ chối) -> ABSTAIN với reason_code tương ứng.
    3. Còn lại (greeting/clarify/answer thành công) -> ANSWER.
    """
    if state.get("intent") == "pure_statutory":
        return "OUT_OF_SCOPE", None
    escalate_reason = state.get("escalate_reason")
    if escalate_reason in _ABSTAIN_REASON_CODE:
        return "ABSTAIN", _ABSTAIN_REASON_CODE[escalate_reason]
    return "ANSWER", None


def sanitize_citations(citations: list[dict]) -> list[Citation]:
    sanitized = []
    for item in citations:
        safe_item = dict(item)
        for field in ("source_file", "title", "category", "excerpt"):
            safe_item[field], _ = redact_pii(str(safe_item.get(field, "")))
        sanitized.append(Citation(**safe_item))
    return sanitized


def _sanitize_response(state: AgentState) -> str:
    response, pii_found = redact_pii(state.get("response", ""))
    if pii_found:
        state["guardrail_pii_redacted"] = True
    return response


def _build_ticket_draft(state: AgentState) -> TicketDraft | None:
    if not state.get("escalate"):
        return None
    return TicketDraft(
        employee_question=state.get("query", ""),
        escalate_reason=state.get("escalate_reason", "low_confidence"),
        confidence_score=state.get("confidence_score"),
        category=state.get("ticket_category"),
        target_department=state.get("ticket_department", "HRBP"),
        priority=state.get("ticket_priority", "Medium"),
    )


def _build_boundary(state: AgentState) -> BoundaryDecisionDTO | None:
    """State luôn có `boundary` khi graph chạy đủ node; giữ nullable để test
    gọi thẳng một node lẻ hoặc client bản cũ vẫn hợp lệ."""
    decision = state.get("boundary")
    return BoundaryDecisionDTO.model_validate(decision) if decision else None


def _network_summary(calls: list[dict]) -> list[dict]:
    """Rút gọn trace của llm_trace về đúng phần đọc được trong log.

    Giữ nguyên THỨ TỰ gọi — thứ tự chính là thứ cho biết một request đã phải
    generate lại mấy lần (cặp chat/chat lặp lại), thứ mà tổng cộng dồn theo
    `kind` giấu mất. Không mang theo prompt/nội dung, chỉ số đo.
    """
    return [
        {
            "kind": call["kind"],
            "model": call["model"],
            "ms": call["duration_ms"],
            **({"attempts": call["attempts"]} if call["attempts"] > 1 else {}),
            **({"ctok": call["completion_tokens"]} if call.get("completion_tokens") else {}),
            **({"reasoning_chars": call["reasoning_chars"]} if call.get("reasoning_chars") else {}),
        }
        for call in calls
    ]


def _log_audit(
    state: AgentState,
    stage_timings_ms: dict[str, int] | None = None,
    network_calls: list[dict] | None = None,
) -> None:
    """Audit trail tối thiểu cho mỗi lượt trả lời — 1 dòng JSON/request, đọc
    được bằng log aggregator bất kỳ (Render/Docker log) mà không cần hạ tầng
    mới. Cố tình KHÔNG log `query` (nội dung câu hỏi thô của nhân viên) — audit
    trail không nên tự trở thành nơi lưu PII/dữ liệu nhạy cảm ngoài ý muốn.

    # ponytail: print thay vì logging module, khớp convention log hiện có của
    # codebase (`print(f"[hybrid] ...")`/`print(f"[rerank] ...")` trong
    # retrieval.py) — nâng cấp lên logging module có level/handler khi cần export
    # sang hệ thống log tập trung thật.
    """
    audit = {
        "intent": state.get("intent"),
        "confidence_score": state.get("confidence_score"),
        "answerable": state.get("answerable"),
        "hallucination_passed": state.get("hallucination_passed"),
        "escalate": state.get("escalate", False),
        "escalate_reason": state.get("escalate_reason"),
        "citation_count": len(state.get("citations", [])),
        "guardrail_injection_detected": state.get("guardrail_injection_detected", False),
        "guardrail_pii_redacted": state.get("guardrail_pii_redacted", False),
    }
    # Telemetry escalation guard — chỉ log khi fast router định escalate, để
    # phân biệt được "guard không chạy" với "guard chạy mà không tốn LLM".
    # verifier_trigger_rate và verifier_useful_rate tính trực tiếp từ 2 trường
    # này (xem AgentState.verifier_*); useful_rate tụt là tín hiệu mở task thêm
    # pre-filter trước verifier.
    if "verifier_called" in state:
        audit["verifier_called"] = state["verifier_called"]
        if state["verifier_called"]:
            audit["verifier_changed_route"] = state.get("verifier_changed_route", False)
            audit["verifier_latency_ms"] = state.get("verifier_latency_ms")
    if state.get("whitelist_shadow_would_block"):
        audit["whitelist_shadow_would_block"] = True
    if state.get("whitelist_blocked"):
        audit["whitelist_blocked"] = True
    if stage_timings_ms is not None:
        audit["stage_timings_ms"] = stage_timings_ms
    if network_calls:
        audit["network_calls"] = _network_summary(network_calls)
    print(f"[audit] {json.dumps(audit, ensure_ascii=False)}")


def _chunk_answer_text(text: str, words_per_chunk: int = _ANSWER_CHUNK_WORDS) -> list[str]:
    """Chia câu trả lời ĐÃ QUA GUARDRAIL thành cụm từ nhỏ để stream — không phải
    token thật từ LLM (xem docstring astream_answer). Giữ khoảng trắng đầu mỗi
    cụm (trừ cụm đầu tiên) để nối lại nguyên văn ở phía client."""
    words = text.split(" ")
    if not words or words == [""]:
        return []
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        piece = " ".join(words[i : i + words_per_chunk])
        chunks.append(piece if i == 0 else f" {piece}")
    return chunks


_IDENTITY_FIELDS = ("tenant_id", "user_id", "department", "user_role", "request_id")


def _initial_state(
    query: str,
    history: list[dict] | None = None,
    identity: dict[str, Any] | None = None,
) -> AgentState:
    """Build state only from identity verified at the internal API boundary."""
    state: AgentState = {"query": query, "history": history or []}
    if identity:
        for field in _IDENTITY_FIELDS:
            value = identity.get(field)
            if value is not None:
                state[field] = value
    return state


async def astream_answer(
    query: str,
    history: list[dict] | None = None,
    identity: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Phiên bản streaming của `answer()` — phát event trong lúc graph chạy
    thay vì chờ toàn bộ ~15-35s rồi trả 1 cục.

    QUYẾT ĐỊNH KIẾN TRÚC (trao đổi với Ted 2026-08-10): KHÔNG stream token thô
    từ LLM ở generate_node. Lý do: hallucination_check/confidence/redact_pii
    chạy SAU generate_node và có thể FAIL/retry/cap điểm/che PII — tức là có
    thể huỷ hoặc sửa toàn bộ câu trả lời. Stream token sống nghĩa là user thấy
    nội dung chưa qua kiểm chứng, đúng lỗ hổng mà route_after_generate
    (src/agents/graph.py) đã cố tình KHÔNG cho phép bỏ qua (xem comment ở đó
    về 7 câu reranker tự tin nhưng sai — check groundedness không được bỏ).

    Thay vào đó, 2 luồng event tách biệt:
    1. `status`/`tool_start`/`tool_end` — phát LIVE ngay khi mỗi node hoàn
       thành (`agent.astream(..., stream_mode="updates")`), chỉ là metadata
       tiến trình, không chứa nội dung câu trả lời -> an toàn tuyệt đối để
       stream ngay, giải quyết đúng vấn đề "màn hình chết 15-35s".
    2. `answer_delta`/`citation` — chỉ phát SAU KHI graph chạy xong toàn bộ
       (đã qua mọi guardrail, giống hệt `answer()`), rồi chia nhỏ theo cụm từ.
       Đây KHÔNG giảm latency tới ký tự đầu tiên của câu trả lời, chỉ tạo hiệu
       ứng gõ chữ mượt cho phần đã được duyệt — đánh đổi có chủ đích, không
       phải hạn chế chưa biết.

    # ponytail: gửi chunk ngay khi sẵn sàng, KHÔNG thêm delay giả lập giữa các
    # chunk (asyncio.sleep) — vì toàn bộ text đã có sẵn cùng lúc, thêm delay là
    # làm chậm giả tạo. Nếu cần hiệu ứng gõ chữ chậm hơn, làm ở client
    # (CSS/JS), không phải ở backend.
    """
    state = _initial_state(query, history, identity)
    started_at = time.perf_counter()
    previous_node_at = started_at
    stage_timings_ms: dict[str, int] = {}
    # Trace chỉ cần SỐNG trong lúc graph chạy; list thu được vẫn đọc bình thường
    # sau khi thoát context, nên đóng nó trước _log_audit là đúng ý.
    profiling = get_settings().profile_latency
    capture_cm = llm_trace.capture() if profiling else None
    network_calls: list[dict] = capture_cm.__enter__() if capture_cm is not None else []
    try:
        has_history = bool(state.get("history"))
        yield {
            "type": "status",
            "value": "Đang xử lý ngữ cảnh hội thoại..." if has_history else "Đang phân tích yêu cầu...",
        }
        async for mode, step in agent.astream(state, stream_mode=["updates", "custom"]):
            if mode == "custom":
                # Tiến trình tool call của react_node (AGENT_MODE=react).
                yield step
                continue
            for node_name, delta in step.items():
                node_completed_at = time.perf_counter()
                elapsed_ms = round((node_completed_at - previous_node_at) * 1000)
                stage_timings_ms[node_name] = stage_timings_ms.get(node_name, 0) + elapsed_ms
                previous_node_at = node_completed_at
                state.update(delta)
                if node_name == "condense" and has_history:
                    yield {"type": "status", "value": "Đang phân tích yêu cầu..."}
                elif node_name == "router":
                    if state.get("intent") == "hr_question":
                        yield {"type": "tool_start", "tool": _RETRIEVE_TOOL_NAME}
                        yield {"type": "status", "value": "Đang tìm trong tài liệu HR..."}
                    else:
                        yield {"type": "status", "value": "Đang soạn câu trả lời..."}
                elif node_name == "retrieve":
                    yield {"type": "tool_end", "tool": _RETRIEVE_TOOL_NAME}
                    yield {"type": "status", "value": "Đang đánh giá các tài liệu tìm được..."}
                elif node_name == "grade":
                    message = (
                        "Đang soạn câu trả lời..."
                        if state.get("retrieved_chunks")
                        else "Đang mở rộng phạm vi tìm kiếm..."
                    )
                    yield {"type": "status", "value": message}
                elif node_name == "rewrite":
                    yield {"type": "tool_start", "tool": _RETRIEVE_TOOL_NAME}
                    yield {"type": "status", "value": "Đang tìm lại với truy vấn chính xác hơn..."}
                elif node_name == "react":
                    yield {"type": "status", "value": "Đang soạn câu trả lời..."}
                elif node_name == "generate":
                    yield {"type": "status", "value": "Đang kiểm tra độ chính xác câu trả lời..."}
                elif node_name == "hallucination_check" and not state.get("hallucination_passed", True):
                    yield {"type": "status", "value": "Đang điều chỉnh câu trả lời theo nguồn..."}
                elif node_name == "escalate_ticket":
                    yield {"type": "status", "value": "Đang chuẩn bị chuyển yêu cầu hỗ trợ..."}
    except Exception as e:  # noqa: BLE001 — báo lỗi qua event thay vì làm rơi kết nối SSE trần trụi
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
        return
    finally:
        if capture_cm is not None:
            capture_cm.__exit__(None, None, None)

    safe_response = _sanitize_response(state)
    total_ms = round((time.perf_counter() - started_at) * 1000)
    stage_timings_ms["total"] = total_ms
    runtime_state, reason_code = _derive_runtime_state(state)
    print(f"[TIMING] [TOTAL PIPELINE] {total_ms}ms ({round(total_ms/1000, 2)}s) | status={runtime_state} | intent={state.get('intent')}")
    _log_audit(state, stage_timings_ms, network_calls)

    safe_citations = sanitize_citations(state.get("citations", []))
    ticket_draft = _build_ticket_draft(state)
    runtime_state, reason_code = _derive_runtime_state(state)
    # Safety: quick_prompts chỉ được phép non-empty khi intent=capability_discovery
    _quick_prompts = state.get("quick_prompts", [])
    if _quick_prompts and state.get("intent") != "capability_discovery":
        _quick_prompts = []
    final_answer = AgentAnswer(
        response=safe_response,
        intent=state.get("intent", "hr_question"),
        confidence_score=state.get("confidence_score"),
        citations=safe_citations,
        needs_clarification=state.get("needs_clarification", False),
        clarifying_question=state.get("clarifying_question"),
        escalate=state.get("escalate", False),
        escalate_reason=state.get("escalate_reason"),
        ticket_draft=ticket_draft,
        boundary=_build_boundary(state),
        state=runtime_state,
        reason_code=reason_code,
        answer_type=state.get("answer_type"),
        quick_prompts=_quick_prompts,
    )

    for chunk in _chunk_answer_text(safe_response):
        yield {"type": "answer_delta", "content": chunk}

    for citation in safe_citations:
        yield {
            "type": "citation",
            "source": citation.source_file,
            "title": citation.title,
            "page_start": citation.page_start,
            "is_official_policy": citation.is_official_policy,
            "public_url": citation.public_url,
            "document_id": citation.document_id,
            "excerpt": citation.excerpt,
            "section": citation.source_section,
        }

    yield {
        "type": "done",
        "intent": state.get("intent"),
        "confidence_score": state.get("confidence_score"),
        "needs_clarification": state.get("needs_clarification", False),
        "clarifying_question": state.get("clarifying_question"),
        "escalate": state.get("escalate", False),
        "escalate_reason": state.get("escalate_reason"),
        "ticket_draft": ticket_draft.model_dump() if ticket_draft else None,
        "boundary": final_answer.boundary.model_dump() if final_answer.boundary else None,
        "state": runtime_state,
        "reason_code": reason_code,
        # Contract hoàn chỉnh giúp service trung gian persist kết quả mà không
        # phải tự ghép lại các event hiển thị như answer_delta/citation.
        "answer": final_answer.model_dump(),
    }


async def answer(
    query: str,
    history: list[dict] | None = None,
    identity: dict[str, Any] | None = None,
) -> AgentAnswer:
    # Đường non-stream (Backend polling) trước đây không có số đo nào ngoài tổng
    # thời gian mà Backend tự bấm giờ, nên không phân biệt được "agent chậm" với
    # "mạng giữa hai service chậm". Chỉ bật khi `profile_latency`.
    profiling = get_settings().profile_latency
    started_at = time.perf_counter()
    capture_cm = llm_trace.capture() if profiling else None
    network_calls: list[dict] = capture_cm.__enter__() if capture_cm is not None else []
    try:
        state: AgentState = await agent.ainvoke(_initial_state(query, history, identity))
    finally:
        if capture_cm is not None:
            capture_cm.__exit__(None, None, None)
    safe_response = _sanitize_response(state)
    total_ms = round((time.perf_counter() - started_at) * 1000)
    runtime_state, reason_code = _derive_runtime_state(state)
    print(f"[TIMING] [TOTAL PIPELINE] {total_ms}ms ({round(total_ms/1000, 2)}s) | status={runtime_state} | intent={state.get('intent')}")
    _log_audit(state, {"total": total_ms} if profiling else None, network_calls)
    # Safety: quick_prompts chỉ được phép non-empty khi intent=capability_discovery
    _quick_prompts = state.get("quick_prompts", [])
    if _quick_prompts and state.get("intent") != "capability_discovery":
        _quick_prompts = []
    return AgentAnswer(
        response=safe_response,
        intent=state.get("intent", "hr_question"),
        confidence_score=state.get("confidence_score"),
        citations=[Citation(**item) for item in state.get("citations", [])],
        needs_clarification=state.get("needs_clarification", False),
        clarifying_question=state.get("clarifying_question"),
        escalate=state.get("escalate", False),
        escalate_reason=state.get("escalate_reason"),
        ticket_draft=_build_ticket_draft(state),
        boundary=_build_boundary(state),
        state=runtime_state,
        reason_code=reason_code,
        answer_type=state.get("answer_type"),
        quick_prompts=_quick_prompts,
    )

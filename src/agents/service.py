"""Điểm vào duy nhất mà lớp bên ngoài (API, backend team, script debug) cần
biết để gọi agent — bọc `agent.ainvoke()` và dịch `AgentState` (TypedDict nội
bộ, có field runtime-only như `rewrite_count`/`hallucination_retry_count`)
sang `AgentAnswer` (Pydantic, contract ổn định — xem docs/AGENT_API.md).

Trước bản này, src/api/routes.py tự đọc `result.get("response")` trực tiếp từ
AgentState và vứt bỏ toàn bộ citations/confidence/escalate/ticket draft ngay
tại lớp gọi — backend không có cách nào lấy lại các trường đó mà không tự đọc
state nội bộ của agent.
"""

from src.agents.graph import agent
from src.agents.state import AgentState
from src.models.schemas import AgentAnswer, Citation, TicketDraft


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


async def answer(query: str) -> AgentAnswer:
    state: AgentState = await agent.ainvoke({"query": query})

    return AgentAnswer(
        response=state.get("response", ""),
        intent=state.get("intent", "hr_question"),
        confidence_score=state.get("confidence_score"),
        citations=[Citation(**c) for c in state.get("citations", [])],
        needs_clarification=state.get("needs_clarification", False),
        clarifying_question=state.get("clarifying_question"),
        escalate=state.get("escalate", False),
        escalate_reason=state.get("escalate_reason"),
        ticket_draft=_build_ticket_draft(state),
    )

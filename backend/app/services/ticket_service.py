import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ticket import TicketDB
from app.schemas.agent import AgentTicketDraftDTO


class TicketService:
    @staticmethod
    async def create_from_agent_draft(
        db: AsyncSession,
        draft: AgentTicketDraftDTO,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        requester_id: uuid.UUID,
    ) -> TicketDB:
        ticket_id = uuid.uuid4()
        ticket = TicketDB(
            id=ticket_id,
            ticket_code=f"TCK-{datetime.now(UTC).year}-{ticket_id.hex[:8].upper()}",
            conversation_id=conversation_id,
            message_id=message_id,
            requester_id=requester_id,
            employee_question=draft.employee_question,
            escalate_reason=draft.escalate_reason,
            confidence_score=draft.confidence_score if draft.confidence_score is not None else 0.0,
            category=draft.category or "GENERAL",
            target_department=draft.target_department,
            priority=draft.priority.strip().capitalize(),
            status="open",
        )
        db.add(ticket)
        await db.flush()
        return ticket

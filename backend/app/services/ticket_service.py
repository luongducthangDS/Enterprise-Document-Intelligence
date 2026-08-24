import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.models.profile import ProfileDB
from app.domain.models.ticket import TicketDB
from app.schemas.agent import AgentTicketDraftDTO
from app.schemas.ticket import TicketCreateRequest, TicketUpdateRequest
from app.services.access_control import DEPARTMENT_MANAGER, SUPER_ADMIN, department_targets


class TicketService:
    @staticmethod
    def _serialize_ticket(ticket: TicketDB) -> dict[str, Any]:
        requester_name = ticket.requester.display_name if ticket.requester else None
        assignee_name = ticket.assignee.display_name if ticket.assignee else None
        return {
            "id": str(ticket.id),
            "ticket_code": ticket.ticket_code,
            "conversation_id": str(ticket.conversation_id) if ticket.conversation_id else None,
            "message_id": str(ticket.message_id) if ticket.message_id else None,
            "requester_id": str(ticket.requester_id),
            "requester_name": requester_name,
            "employee_question": ticket.employee_question,
            "escalate_reason": ticket.escalate_reason,
            "confidence_score": float(ticket.confidence_score) if ticket.confidence_score is not None else None,
            "category": ticket.category or "GENERAL",
            "target_department": ticket.target_department,
            "priority": ticket.priority,
            "status": ticket.status,
            "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            "assignee_name": assignee_name,
            "resolution_note": ticket.resolution_note,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        }

    @classmethod
    async def create_from_agent_draft(
        cls,
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

    @classmethod
    async def create_ticket(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        data: TicketCreateRequest,
    ) -> dict[str, Any]:
        requester_id = uuid.UUID(user["user_id"])

        profile_stmt = select(ProfileDB).where(ProfileDB.id == requester_id)
        profile_res = await db.execute(profile_stmt)
        profile = profile_res.scalars().first()
        if not profile:
            raise NotFoundError(code="PROFILE_NOT_FOUND", message="Hồ sơ người dùng không tồn tại.")

        ticket_id = uuid.uuid4()
        ticket_code = f"TCK-{datetime.now(UTC).year}-{ticket_id.hex[:8].upper()}"

        dept = (data.target_department or "HRBP").upper()
        if dept not in ("CB", "ER", "TA", "LD", "HRBP"):
            dept = "HRBP"

        prio = (data.priority or "Medium").strip().capitalize()
        if prio not in ("Low", "Medium", "High"):
            prio = "Medium"

        reason = (data.escalate_reason or "user_requested_human").lower()
        if reason not in ("low_confidence", "out_of_scope", "personal_data_required", "user_requested_human"):
            reason = "user_requested_human"

        ticket = TicketDB(
            id=ticket_id,
            ticket_code=ticket_code,
            conversation_id=data.conversation_id,
            message_id=data.message_id,
            requester_id=requester_id,
            employee_question=data.employee_question,
            escalate_reason=reason,
            confidence_score=data.confidence_score,
            category=data.category or "GENERAL",
            target_department=dept,
            priority=prio,
            status="open",
        )
        db.add(ticket)
        await db.commit()

        stmt = (
            select(TicketDB)
            .options(joinedload(TicketDB.requester), joinedload(TicketDB.assignee))
            .where(TicketDB.id == ticket_id)
        )
        res = await db.execute(stmt)
        saved_ticket = res.scalar_one()

        return cls._serialize_ticket(saved_ticket)

    @classmethod
    async def list_tickets(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        status_filter: str | None = None,
        department_filter: str | None = None,
        priority_filter: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        user_id = uuid.UUID(user["user_id"])
        user_role = str(user.get("role", "employee")).upper()

        stmt = select(TicketDB).options(joinedload(TicketDB.requester), joinedload(TicketDB.assignee))

        if user_role == DEPARTMENT_MANAGER:
            stmt = stmt.where(TicketDB.target_department.in_(department_targets(user.get("department"))))
        elif user_role != SUPER_ADMIN:
            stmt = stmt.where(TicketDB.requester_id == user_id)

        if status_filter:
            stmt = stmt.where(TicketDB.status == status_filter.lower())
        if department_filter:
            stmt = stmt.where(TicketDB.target_department == department_filter.upper())
        if priority_filter:
            stmt = stmt.where(TicketDB.priority == priority_filter.strip().capitalize())

        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
                stmt = stmt.where(TicketDB.created_at < cursor_dt)
            except ValueError:
                pass

        stmt = stmt.order_by(desc(TicketDB.created_at)).limit(limit + 1)
        res = await db.execute(stmt)
        tickets = list(res.scalars().all())

        has_more = len(tickets) > limit
        if has_more:
            tickets = tickets[:limit]
            next_cursor = tickets[-1].created_at.isoformat() if tickets else None
        else:
            next_cursor = None

        data_list = [cls._serialize_ticket(t) for t in tickets]
        pagination = {"has_more": has_more, "next_cursor": next_cursor, "limit": limit}
        return data_list, pagination

    @classmethod
    async def get_ticket_detail(
        cls,
        db: AsyncSession,
        ticket_id: str,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            t_uuid = uuid.UUID(ticket_id)
        except ValueError:
            raise NotFoundError(code="TICKET_NOT_FOUND", message="Không tìm thấy ticket hỗ trợ.")

        stmt = (
            select(TicketDB)
            .options(joinedload(TicketDB.requester), joinedload(TicketDB.assignee))
            .where(TicketDB.id == t_uuid)
        )
        res = await db.execute(stmt)
        ticket = res.scalars().first()
        if not ticket:
            raise NotFoundError(code="TICKET_NOT_FOUND", message="Không tìm thấy ticket hỗ trợ.")

        user_id = uuid.UUID(user["user_id"])
        user_role = str(user.get("role", "employee")).upper()

        manages_department = (
            user_role == DEPARTMENT_MANAGER
            and ticket.target_department.upper() in department_targets(user.get("department"))
        )
        if user_role != SUPER_ADMIN and not manages_department and ticket.requester_id != user_id:
            raise ForbiddenError(code="TICKET_ACCESS_DENIED", message="Bạn không có quyền xem ticket này.")

        return cls._serialize_ticket(ticket)

    @classmethod
    async def update_ticket(
        cls,
        db: AsyncSession,
        ticket_id: str,
        user: dict[str, Any],
        data: TicketUpdateRequest,
    ) -> dict[str, Any]:
        try:
            t_uuid = uuid.UUID(ticket_id)
        except ValueError:
            raise NotFoundError(code="TICKET_NOT_FOUND", message="Không tìm thấy ticket hỗ trợ.")

        stmt = (
            select(TicketDB)
            .options(joinedload(TicketDB.requester), joinedload(TicketDB.assignee))
            .where(TicketDB.id == t_uuid)
        )
        res = await db.execute(stmt)
        ticket = res.scalars().first()
        if not ticket:
            raise NotFoundError(code="TICKET_NOT_FOUND", message="Không tìm thấy ticket hỗ trợ.")

        user_role = str(user.get("role", "employee")).upper()
        user_id = uuid.UUID(user["user_id"])
        is_admin = user_role == SUPER_ADMIN or (
            user_role == DEPARTMENT_MANAGER
            and ticket.target_department.upper() in department_targets(user.get("department"))
        )
        requested_status = data.status.lower() if data.status is not None else None
        if not is_admin:
            if ticket.requester_id != user_id:
                raise ForbiddenError(code="FORBIDDEN", message="Bạn không có quyền cập nhật ticket hỗ trợ.")
            if requested_status != "closed" or any(
                value is not None for value in (data.assignee_id, data.resolution_note, data.priority)
            ):
                raise ForbiddenError(
                    code="FORBIDDEN",
                    message="Người tạo chỉ được xác nhận đóng ticket đã xử lý xong.",
                )
            if ticket.status.lower() != "resolved":
                raise ConflictError(
                    code="TICKET_NOT_RESOLVED",
                    message="Chỉ có thể đóng ticket sau khi HR đã hoàn tất xử lý.",
                )

        if data.status is not None:
            new_status = requested_status or ""
            if new_status not in ("open", "in_progress", "resolved", "closed"):
                raise ConflictError(code="INVALID_TICKET_STATUS", message="Trạng thái ticket không hợp lệ.")
            if new_status in ("resolved", "closed") and not (data.resolution_note or ticket.resolution_note):
                raise ConflictError(
                    code="RESOLUTION_NOTE_REQUIRED",
                    message="Cần nhập kết quả xử lý trước khi hoàn tất ticket.",
                )
            ticket.status = new_status
            if new_status == "in_progress" and ticket.assignee_id is None:
                ticket.assignee_id = user_id
            if new_status == "resolved":
                ticket.resolved_at = datetime.now(UTC)
                ticket.closed_at = None
            elif new_status == "closed":
                ticket.resolved_at = ticket.resolved_at or datetime.now(UTC)
                ticket.closed_at = datetime.now(UTC)
            else:
                ticket.resolved_at = None
                ticket.closed_at = None

        if data.assignee_id is not None:
            ticket.assignee_id = data.assignee_id

        if data.resolution_note is not None:
            ticket.resolution_note = data.resolution_note

        if data.priority is not None:
            prio = data.priority.strip().capitalize()
            if prio in ("Low", "Medium", "High"):
                ticket.priority = prio

        ticket.updated_at = datetime.now(UTC)
        await db.commit()

        res = await db.execute(stmt)
        updated_ticket = res.scalar_one()

        return cls._serialize_ticket(updated_ticket)

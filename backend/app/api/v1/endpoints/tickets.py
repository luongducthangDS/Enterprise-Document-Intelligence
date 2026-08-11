from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user, require_role
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.schemas.ticket import TicketCreateRequest, TicketUpdateRequest
from app.services.ticket_service import TicketService

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request_data: TicketCreateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Tạo HR Ticket hỗ trợ (Auto Escalation hoặc tạo thủ công). Yêu cầu đăng nhập JWT."""
    data = await TicketService.create_ticket(db, current_user, request_data)
    return wrap_response(data, request)


@router.get("")
async def list_tickets(
    request: Request,
    ticket_status: str | None = Query(None, alias="status"),
    target_department: str | None = Query(None, alias="department"),
    priority: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Danh sách ticket hỗ trợ (Employee xem ticket cá nhân, HR Admin xem tất cả/lọc). Yêu cầu đăng nhập JWT."""
    data, pagination = await TicketService.list_tickets(
        db=db,
        user=current_user,
        status_filter=ticket_status,
        department_filter=target_department,
        priority_filter=priority,
        limit=limit,
        cursor=cursor,
    )
    return wrap_response(data, request, pagination=pagination)


@router.get("/{ticket_id}")
async def get_ticket_detail(
    ticket_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lấy chi tiết ticket hỗ trợ. Yêu cầu đăng nhập JWT."""
    data = await TicketService.get_ticket_detail(db, ticket_id, current_user)
    return wrap_response(data, request)


@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    payload: TicketUpdateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_role(["hr_admin", "super_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật trạng thái / người xử lý / ghi chú cho ticket (chỉ HR Admin / Super Admin)."""
    data = await TicketService.update_ticket(db, ticket_id, current_user, payload)
    return wrap_response(data, request)

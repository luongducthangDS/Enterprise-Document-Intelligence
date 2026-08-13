import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.schemas.conversations import CreateConversationRequest, UpdateConversationRequest
from app.services.conversation_service import ConversationService

router = APIRouter()


@router.get("")
async def list_conversations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lấy danh sách cuộc hội thoại gần đây của người dùng."""
    user_id = uuid.UUID(current_user["user_id"])
    data = await ConversationService.list_conversations(db, user_id, limit)
    return wrap_response(data, request)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request_data: CreateConversationRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Tạo cuộc hội thoại mới."""
    user_id = uuid.UUID(current_user["user_id"])
    data = await ConversationService.create_conversation(db, user_id, request_data.title)
    return wrap_response(data, request)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lấy thông tin chi tiết phiên hội thoại."""
    user_id = uuid.UUID(current_user["user_id"])
    data = await ConversationService.get_conversation(db, conversation_id, user_id)
    return wrap_response(data, request)


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: uuid.UUID,
    request_data: UpdateConversationRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Đổi tên cuộc hội thoại của người dùng hiện tại."""
    user_id = uuid.UUID(current_user["user_id"])
    data = await ConversationService.rename_conversation(db, conversation_id, user_id, request_data.title)
    return wrap_response(data, request)


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lấy lịch sử tin nhắn của cuộc hội thoại (Cursor-based pagination)."""
    user_id = uuid.UUID(current_user["user_id"])
    res_data = await ConversationService.get_conversation_messages(db, conversation_id, user_id, limit, cursor)
    pagination = res_data.pop("pagination", None)
    return wrap_response(res_data, request, pagination=pagination)


@router.post("/{conversation_id}/end")
async def end_conversation(
    conversation_id: uuid.UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Kết thúc phiên hội thoại."""
    user_id = uuid.UUID(current_user["user_id"])
    data = await ConversationService.end_conversation(db, conversation_id, user_id)
    return wrap_response(data, request)

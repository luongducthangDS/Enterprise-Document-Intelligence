import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.chat import CreateChatRequestSchema, RetryChatRequestSchema
from app.schemas.common import wrap_response
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("/requests", status_code=status.HTTP_202_ACCEPTED)
async def submit_chat_request(
    request_data: CreateChatRequestSchema,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Gửi câu hỏi RAG mới (Trả về 202 Accepted + poll_after_ms để FE thực hiện polling)."""
    user_id = uuid.UUID(current_user["user_id"])
    department = current_user.get("department", "GENERAL")
    conversation_id = uuid.UUID(request_data.conversation_id)

    data = await ChatService.submit_chat_request(
        db=db,
        user_id=user_id,
        department=department,
        conversation_id=conversation_id,
        question=request_data.question,
    )
    return wrap_response(data, request)


@router.get("/requests/{chat_request_id}")
async def get_chat_request_status(
    chat_request_id: uuid.UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lấy trạng thái và kết quả trả lời của yêu cầu Chat RAG (Polling endpoint)."""
    user_id = uuid.UUID(current_user["user_id"])
    data = await ChatService.get_chat_request_status(
        db=db,
        chat_request_id=chat_request_id,
        user_id=user_id,
    )
    return wrap_response(data, request)


@router.post("/requests/{chat_request_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_chat_request(
    chat_request_id: uuid.UUID,
    request: Request,
    retry_data: RetryChatRequestSchema | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Thử lại yêu cầu Chat RAG đối với các request bị lỗi hoặc cho phép retry."""
    user_id = uuid.UUID(current_user["user_id"])
    department = current_user.get("department", "GENERAL")
    reason = retry_data.reason if retry_data else "USER_RETRY"

    data = await ChatService.retry_chat_request(
        db=db,
        chat_request_id=chat_request_id,
        user_id=user_id,
        department=department,
        reason=reason,
    )
    return wrap_response(data, request)

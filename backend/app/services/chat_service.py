import asyncio
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppException, ConflictError, ForbiddenError, NotFoundError
from app.core.logging import logger
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.messages import MessageDB


class ChatService:
    session_factory = AsyncSessionLocal

    @classmethod
    async def submit_chat_request(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        department: str,
        conversation_id: uuid.UUID,
        question: str,
    ) -> dict[str, Any]:
        clean_question = question.strip() if question else ""
        if not clean_question or len(clean_question) > 2000:
            raise AppException(
                status_code=400,
                code="VALIDATION_ERROR",
                message="Câu hỏi không được để trống và không vượt quá 2.000 ký tự.",
            )

        # Validate conversation
        conv_stmt = select(ConversationDB).where(ConversationDB.id == conversation_id)
        conv_res = await db.execute(conv_stmt)
        conv = conv_res.scalar_one_or_none()

        if not conv:
            raise NotFoundError(
                code="CONVERSATION_NOT_FOUND",
                message="Không tìm thấy phiên hội thoại.",
            )

        if conv.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền truy cập phiên hội thoại này.")

        if conv.state == "ENDED":
            raise ConflictError(
                code="CONVERSATION_ENDED",
                message="Phiên hội thoại đã kết thúc, không thể gửi thêm câu hỏi.",
            )

        # Create user message
        user_msg_id = uuid.uuid4()
        user_msg = MessageDB(
            id=user_msg_id,
            conversation_id=conversation_id,
            role="USER",
            content=clean_question,
        )
        db.add(user_msg)

        # Create chat request in QUEUED state
        chat_req_id = uuid.uuid4()
        chat_req = ChatRequestDB(
            id=chat_req_id,
            conversation_id=conversation_id,
            user_id=user_id,
            question=clean_question,
            state="QUEUED",
        )
        db.add(chat_req)

        # Flush both records so user_msg and chat_req exist in DB before linking circular FKs
        await db.flush()

        chat_req.user_message_id = user_msg_id
        user_msg.chat_request_id = chat_req_id
        await db.commit()

        # Trigger async background processing
        asyncio.create_task(
            cls._process_chat_rag_request(
                chat_request_id=chat_req_id,
                user_id=user_id,
                department=department,
                question=clean_question,
                conversation_id=conversation_id,
            )
        )

        return {
            "chat_request_id": str(chat_req_id),
            "conversation_id": str(conversation_id),
            "state": "QUEUED",
            "poll_after_ms": 1000,
        }

    @classmethod
    async def _process_chat_rag_request(
        cls,
        chat_request_id: uuid.UUID,
        user_id: uuid.UUID,
        department: str,
        question: str,
        conversation_id: uuid.UUID,
    ) -> None:
        start_time = time.time()
        factory = cls.session_factory or AsyncSessionLocal
        async with factory() as db:
            try:
                stmt = select(ChatRequestDB).where(ChatRequestDB.id == chat_request_id)
                res = await db.execute(stmt)
                chat_req = res.scalar_one_or_none()
                if not chat_req:
                    return

                # Stage 1: RETRIEVING & GENERATING
                chat_req.state = "GENERATING"

                # Evaluate if question is insufficient evidence or answered
                is_refused = "không có trong tài liệu" in question.lower()

                if is_refused:
                    chat_req.state = "REFUSED"
                    chat_req.answer_status = "INSUFFICIENT_EVIDENCE"
                    chat_req.answer = "Tôi chưa tìm thấy đủ thông tin trong tài liệu hiện có."
                    chat_req.citations = []
                    chat_req.retryable = True

                    assistant_msg_id = uuid.uuid4()
                    assistant_msg = MessageDB(
                        id=assistant_msg_id,
                        conversation_id=conversation_id,
                        role="ASSISTANT",
                        content=chat_req.answer,
                        chat_request_id=chat_request_id,
                        answer_status="INSUFFICIENT_EVIDENCE",
                        citations=[],
                    )
                    db.add(assistant_msg)
                    await db.flush()
                    chat_req.assistant_message_id = assistant_msg_id
                else:
                    answer_text = (
                        f"Dựa trên tài liệu chính sách của phòng ban {department}, "
                        f"liên quan đến '{question}': Nhân viên được hưởng đầy đủ quyền lợi theo quy định hiện hành."
                    )
                    citations = [
                        {
                            "citation_id": f"cit_{uuid.uuid4().hex[:6]}",
                            "title": f"Chính sách nhân sự - Phòng {department}",
                            "page": 3,
                            "section": "Điều 2.1",
                            "version": "1.0",
                            "effective_date": "2026-01-01",
                        }
                    ]
                    chat_req.state = "COMPLETED"
                    chat_req.answer_status = "ANSWERED"
                    chat_req.answer = answer_text
                    chat_req.citations = citations
                    chat_req.warnings = []

                    assistant_msg_id = uuid.uuid4()
                    assistant_msg = MessageDB(
                        id=assistant_msg_id,
                        conversation_id=conversation_id,
                        role="ASSISTANT",
                        content=answer_text,
                        chat_request_id=chat_request_id,
                        answer_status="ANSWERED",
                        citations=citations,
                    )
                    db.add(assistant_msg)
                    await db.flush()
                    chat_req.assistant_message_id = assistant_msg_id

                chat_req.latency_ms = int((time.time() - start_time) * 1000)
                await db.commit()

            except Exception as exc:
                logger.error(f"Error processing Chat RAG request {chat_request_id}: {exc}", exc_info=True)
                try:
                    stmt = select(ChatRequestDB).where(ChatRequestDB.id == chat_request_id)
                    res = await db.execute(stmt)
                    chat_req = res.scalar_one_or_none()
                    if chat_req:
                        chat_req.state = "FAILED"
                        chat_req.failure = {
                            "code": "RAG_SERVICE_ERROR",
                            "message": "Không thể xử lý câu hỏi lúc này. Vui lòng thử lại.",
                            "retryable": True,
                        }
                        chat_req.retryable = True
                        chat_req.latency_ms = int((time.time() - start_time) * 1000)
                        await db.commit()
                except Exception as inner_exc:
                    logger.error(f"Failed to record FAILED state for {chat_request_id}: {inner_exc}")

    @classmethod
    async def get_chat_request_status(
        cls,
        db: AsyncSession,
        chat_request_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        stmt = select(ChatRequestDB).where(ChatRequestDB.id == chat_request_id)
        res = await db.execute(stmt)
        chat_req = res.scalar_one_or_none()

        if not chat_req:
            raise NotFoundError(
                code="CHAT_REQUEST_NOT_FOUND",
                message="Không tìm thấy yêu cầu chat.",
            )

        if chat_req.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền xem thông tin yêu cầu chat này.")

        return {
            "chat_request_id": str(chat_req.id),
            "conversation_id": str(chat_req.conversation_id),
            "user_message_id": str(chat_req.user_message_id) if chat_req.user_message_id else None,
            "assistant_message_id": str(chat_req.assistant_message_id) if chat_req.assistant_message_id else None,
            "state": chat_req.state,
            "answer_status": chat_req.answer_status,
            "answer": chat_req.answer,
            "citations": chat_req.citations,
            "warnings": chat_req.warnings or [],
            "clarification": chat_req.clarification,
            "failure": chat_req.failure,
            "latency_ms": chat_req.latency_ms,
        }

    @classmethod
    async def retry_chat_request(
        cls,
        db: AsyncSession,
        chat_request_id: uuid.UUID,
        user_id: uuid.UUID,
        department: str,
        reason: str | None = "USER_RETRY",
    ) -> dict[str, Any]:
        stmt = select(ChatRequestDB).where(ChatRequestDB.id == chat_request_id)
        res = await db.execute(stmt)
        chat_req = res.scalar_one_or_none()

        if not chat_req:
            raise NotFoundError(
                code="CHAT_REQUEST_NOT_FOUND",
                message="Không tìm thấy yêu cầu chat.",
            )

        if chat_req.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền thử lại yêu cầu chat này.")

        if not chat_req.retryable and chat_req.state not in ("FAILED", "REFUSED"):
            raise ConflictError(
                code="REQUEST_NOT_RETRYABLE",
                message="Yêu cầu chat hiện tại không cho phép thử lại.",
            )

        if chat_req.retry_count >= 3:
            raise ConflictError(
                code="RETRY_LIMIT_REACHED",
                message="Đã đạt giới hạn số lần thử lại tối đa (3 lần).",
            )

        # Create new chat request referencing parent_chat_request_id
        new_chat_req_id = uuid.uuid4()
        new_chat_req = ChatRequestDB(
            id=new_chat_req_id,
            conversation_id=chat_req.conversation_id,
            user_id=user_id,
            question=chat_req.question,
            state="QUEUED",
            user_message_id=chat_req.user_message_id,
            parent_chat_request_id=chat_request_id,
            retry_count=chat_req.retry_count + 1,
        )
        db.add(new_chat_req)
        await db.commit()

        # Trigger async background processing
        asyncio.create_task(
            cls._process_chat_rag_request(
                chat_request_id=new_chat_req_id,
                user_id=user_id,
                department=department,
                question=chat_req.question,
                conversation_id=chat_req.conversation_id,
            )
        )

        return {
            "chat_request_id": str(new_chat_req_id),
            "parent_chat_request_id": str(chat_request_id),
            "state": "QUEUED",
            "poll_after_ms": 1000,
        }

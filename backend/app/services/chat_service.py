import asyncio
import time
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppException, ConflictError, ForbiddenError, NotFoundError
from app.core.logging import logger
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.messages import MessageDB
from app.services.agent_answer_adapter import AgentAnswerAdapter
from app.services.ai_agent_client import AIAgentClient, AIAgentClientError
from app.services.ticket_service import TicketService


class ChatService:
    session_factory = AsyncSessionLocal
    agent_client = AIAgentClient()
    background_tasks_enabled = True

    @staticmethod
    def _build_clarification_query(
        original_question: str,
        clarifying_question: str,
        clarification_answer: str,
        max_length: int = 2000,
    ) -> str:
        answer = clarification_answer.strip()
        prefix = "Câu hỏi gốc: "
        middle = "\nCâu hỏi làm rõ: "
        suffix = "\nThông tin người dùng bổ sung: "
        fixed_length = len(prefix) + len(middle) + len(suffix) + len(answer)
        context_budget = max(0, max_length - fixed_length)
        original_budget = (context_budget * 2) // 3
        clarifying_budget = context_budget - original_budget
        return (
            f"{prefix}{original_question.strip()[:original_budget]}"
            f"{middle}{clarifying_question.strip()[:clarifying_budget]}"
            f"{suffix}{answer}"
        )[:max_length]

    @classmethod
    async def _resolve_agent_query(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_question: str,
    ) -> str:
        previous_res = await db.execute(
            select(MessageDB)
            .where(MessageDB.conversation_id == conversation_id, MessageDB.role == "ASSISTANT")
            .order_by(MessageDB.created_at.desc())
            .limit(1)
        )
        previous_assistant = previous_res.scalar_one_or_none()
        if (
            not previous_assistant
            or previous_assistant.answer_status != "CLARIFICATION_REQUIRED"
            or not previous_assistant.chat_request_id
        ):
            return user_question

        original_request = await db.get(ChatRequestDB, previous_assistant.chat_request_id)
        if not original_request:
            return user_question
        return cls._build_clarification_query(
            original_question=original_request.question,
            clarifying_question=previous_assistant.content,
            clarification_answer=user_question,
        )

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

        conv_res = await db.execute(select(ConversationDB).where(ConversationDB.id == conversation_id))
        conv = conv_res.scalar_one_or_none()
        if not conv:
            raise NotFoundError(code="CONVERSATION_NOT_FOUND", message="Không tìm thấy phiên hội thoại.")
        if conv.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền truy cập phiên hội thoại này.")
        if conv.state == "ENDED":
            raise ConflictError(
                code="CONVERSATION_ENDED",
                message="Phiên hội thoại đã kết thúc, không thể gửi thêm câu hỏi.",
            )

        agent_query = await cls._resolve_agent_query(db, conversation_id, clean_question)

        user_msg_id = uuid.uuid4()
        user_msg = MessageDB(
            id=user_msg_id,
            conversation_id=conversation_id,
            role="USER",
            content=clean_question,
        )
        db.add(user_msg)

        chat_req_id = uuid.uuid4()
        chat_req = ChatRequestDB(
            id=chat_req_id,
            conversation_id=conversation_id,
            user_id=user_id,
            question=clean_question,
            state="QUEUED",
        )
        db.add(chat_req)
        await db.flush()

        chat_req.user_message_id = user_msg_id
        user_msg.chat_request_id = chat_req_id
        await db.commit()

        if cls.background_tasks_enabled:
            asyncio.create_task(
                cls._process_chat_rag_request(
                    chat_request_id=chat_req_id,
                    user_id=user_id,
                    department=department,
                    question=agent_query,
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
        start_time = time.monotonic()
        factory = cls.session_factory or AsyncSessionLocal
        async with factory() as db:
            try:
                claim = await db.execute(
                    update(ChatRequestDB)
                    .where(ChatRequestDB.id == chat_request_id, ChatRequestDB.state == "QUEUED")
                    .values(state="GENERATING")
                )
                await db.commit()
                if claim.rowcount != 1:
                    return

                agent_answer = await cls.agent_client.query_agent(
                    user_id=str(user_id),
                    query=question,
                    department=department,
                    request_id=str(chat_request_id),
                )
                mapped = AgentAnswerAdapter.map(agent_answer, chat_request_id)

                chat_req = await db.get(ChatRequestDB, chat_request_id)
                if not chat_req or chat_req.assistant_message_id is not None:
                    return

                assistant_msg_id = uuid.uuid4()
                assistant_msg = MessageDB(
                    id=assistant_msg_id,
                    conversation_id=conversation_id,
                    role="ASSISTANT",
                    content=mapped.message_content,
                    chat_request_id=chat_request_id,
                    answer_status=mapped.answer_status,
                    citations=mapped.citations,
                    confidence_score=agent_answer.confidence_score,
                    escalated=agent_answer.escalate,
                )
                db.add(assistant_msg)
                await db.flush()

                if agent_answer.escalate:
                    if agent_answer.ticket_draft is None:
                        raise ValueError("Escalated AgentAnswer is missing ticket_draft")
                    ticket = await TicketService.create_from_agent_draft(
                        db=db,
                        draft=agent_answer.ticket_draft,
                        conversation_id=conversation_id,
                        message_id=assistant_msg_id,
                        requester_id=user_id,
                    )
                    assistant_msg.ticket_id = ticket.id

                chat_req.state = mapped.state
                chat_req.answer_status = mapped.answer_status
                chat_req.answer = mapped.answer
                chat_req.citations = mapped.citations
                chat_req.warnings = mapped.warnings
                chat_req.clarification = mapped.clarification
                chat_req.failure = None
                chat_req.retryable = mapped.retryable
                chat_req.assistant_message_id = assistant_msg_id
                chat_req.latency_ms = int((time.monotonic() - start_time) * 1000)
                await db.commit()

            except Exception as exc:
                logger.error(f"Error processing Chat RAG request {chat_request_id}: {exc}", exc_info=True)
                try:
                    await db.rollback()
                    chat_req = await db.get(ChatRequestDB, chat_request_id)
                    if chat_req:
                        error_code = exc.code if isinstance(exc, AIAgentClientError) else "RAG_SERVICE_ERROR"
                        retryable = exc.retryable if isinstance(exc, AIAgentClientError) else True
                        chat_req.state = "FAILED"
                        chat_req.failure = {
                            "code": error_code,
                            "message": "Không thể xử lý câu hỏi lúc này. Vui lòng thử lại.",
                            "retryable": retryable,
                        }
                        chat_req.retryable = retryable
                        chat_req.latency_ms = int((time.monotonic() - start_time) * 1000)
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
        res = await db.execute(select(ChatRequestDB).where(ChatRequestDB.id == chat_request_id))
        chat_req = res.scalar_one_or_none()
        if not chat_req:
            raise NotFoundError(code="CHAT_REQUEST_NOT_FOUND", message="Không tìm thấy yêu cầu chat.")
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
        res = await db.execute(select(ChatRequestDB).where(ChatRequestDB.id == chat_request_id))
        chat_req = res.scalar_one_or_none()
        if not chat_req:
            raise NotFoundError(code="CHAT_REQUEST_NOT_FOUND", message="Không tìm thấy yêu cầu chat.")
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

        if cls.background_tasks_enabled:
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

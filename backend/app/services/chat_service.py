import asyncio
import socket
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import os
from sqlalchemy import case, desc, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppException, ConflictError, ForbiddenError, NotFoundError
from app.core.logging import logger
from app.domain.models.audit import AuditLogDB
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.documents import DocumentDB
from app.domain.models.messages import MessageDB
from app.domain.models.profile import ProfileDB
from app.schemas.agent import AgentAnswerDTO, AgentTicketDraftDTO
from app.services.agent_answer_adapter import AgentAnswerAdapter
from app.services.ai_agent_client import AIAgentClient, AIAgentClientError
from app.services.content_safety import sanitize_citations_for_client
from app.services.conversation_service import DEFAULT_CONVERSATION_TITLE, make_conversation_title
from app.services.ticket_service import TicketService




def _agent_role(profile_role: str) -> str:
    """Map Backend administrative roles to the Agent's canonical authorization roles."""
    normalized = str(profile_role or "").upper().strip()
    aliases: dict[str, str] = {}
    mapped = aliases.get(normalized, normalized)
    allowed = {"EMPLOYEE", "DEPARTMENT_MANAGER", "SUPER_ADMIN"}
    if mapped not in allowed:
        raise AIAgentClientError("IDENTITY_ROLE_INVALID", f"Unsupported profile role: {normalized}", False)
    return mapped

class ChatService:
    session_factory = AsyncSessionLocal
    agent_client = AIAgentClient()
    background_tasks_enabled = True
    background_tasks: set[asyncio.Task[None]] = set()
    stream_heartbeat_seconds = 15.0

    @classmethod
    def _schedule_chat_request(
        cls,
        *,
        chat_request_id: uuid.UUID,
        user_id: uuid.UUID,
        department: str,
        question: str,
        conversation_id: uuid.UUID,
    ) -> None:
        task = asyncio.create_task(
            cls._process_chat_rag_request(
                chat_request_id=chat_request_id,
                user_id=user_id,
                department=department,
                question=question,
                conversation_id=conversation_id,
            )
        )
        cls.background_tasks.add(task)
        task.add_done_callback(cls.background_tasks.discard)

    @classmethod
    async def recover_pending_requests(cls) -> int:
        if not cls.background_tasks_enabled:
            return 0

        async with cls.session_factory() as db:
            result = await db.execute(
                select(ChatRequestDB)
                .where(ChatRequestDB.state.in_(("QUEUED", "GENERATING")))
                .order_by(ChatRequestDB.created_at.desc())
            )
            pending = list(result.scalars().all())
            cutoff = datetime.now(UTC) - timedelta(minutes=10)
            def _to_utc(dt: datetime | None) -> datetime:
                if dt is None:
                    return datetime.min.replace(tzinfo=UTC)
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

            recoverable = [request for request in pending if _to_utc(request.created_at) >= cutoff][:10]
            recoverable_ids = {request.id for request in recoverable}
            for request in pending:
                if request.id not in recoverable_ids:
                    request.state = "FAILED"
                    request.failure = {
                        "code": "WORKER_RESTARTED",
                        "message": "Yêu cầu bị gián đoạn khi Backend khởi động lại. Vui lòng thử lại.",
                        "retryable": True,
                    }
                    request.retryable = True
                    continue
                request.state = "QUEUED"
            await db.commit()

        for request in recoverable:
            cls._schedule_chat_request(
                chat_request_id=request.id,
                user_id=request.user_id,
                department="GENERAL",
                question=request.question,
                conversation_id=request.conversation_id,
            )
        return len(recoverable)

    @classmethod
    async def cancel_background_tasks(cls) -> None:
        tasks = list(cls.background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        cls.background_tasks.clear()

    @classmethod
    async def _load_agent_history(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        exclude_message_id: uuid.UUID | None = None,
    ) -> list[dict[str, str]]:
        max_turns = get_settings().ai_agent_max_history_turns
        if max_turns == 0:
            return []

        statement = (
            select(MessageDB)
            .where(
                MessageDB.conversation_id == conversation_id,
                func.lower(MessageDB.role).in_(("user", "assistant")),
            )
            .order_by(MessageDB.created_at.desc(), MessageDB.id.desc())
            .limit(max_turns)
        )
        if exclude_message_id is not None:
            statement = statement.where(MessageDB.id != exclude_message_id)

        result = await db.execute(statement)
        messages = list(reversed(result.scalars().all()))
        return [
            {
                "role": message.role.lower(),
                "content": message.content.strip()[:5000],
            }
            for message in messages
            if message.content and message.content.strip()
        ]

    @classmethod
    async def submit_chat_request(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        department: str,
        conversation_id: uuid.UUID,
        question: str,
        start_background: bool | None = None,
        chat_request_id: uuid.UUID | None = None,
        user_message_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        clean_question = question.strip() if question else ""
        if not clean_question:
            raise AppException(
                status_code=400,
                code="VALIDATION_ERROR",
                message="Câu hỏi không được để trống.",
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
        if conv.title == DEFAULT_CONVERSATION_TITLE:
            conv.title = make_conversation_title(clean_question)
        conv.updated_at = datetime.now(UTC)

        user_msg_id = user_message_id or uuid.uuid4()
        chat_req_id = chat_request_id or uuid.uuid4()
        user_msg = MessageDB(
            id=user_msg_id,
            conversation_id=conversation_id,
            role="user",
            content=clean_question,
        )

        chat_req = ChatRequestDB(
            id=chat_req_id,
            conversation_id=conversation_id,
            user_id=user_id,
            question=clean_question,
            state="QUEUED",
        )
        db.add_all([user_msg, chat_req])
        await db.flush()

        chat_req.user_message_id = user_msg_id
        user_msg.chat_request_id = chat_req_id
        await db.commit()

        should_start_background = cls.background_tasks_enabled if start_background is None else start_background
        if should_start_background:
            cls._schedule_chat_request(
                chat_request_id=chat_req_id,
                user_id=user_id,
                department=department,
                question=clean_question,
                conversation_id=conversation_id,
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
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
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

                chat_req = await db.get(ChatRequestDB, chat_request_id)
                if not chat_req or chat_req.assistant_message_id is not None:
                    return
                # Authorization identity comes from Backend DB, never frontend.
                profile = await db.get(ProfileDB, user_id)
                if profile is None:
                    raise AIAgentClientError("IDENTITY_PROFILE_MISSING", "Authenticated profile no longer exists", False)
                if not str(profile.department or "").strip() or not str(profile.role or "").strip():
                    raise AIAgentClientError("IDENTITY_PROFILE_INCOMPLETE", "Profile role/department is incomplete", False)
                effective_department = str(profile.department).upper().strip()
                effective_role = _agent_role(profile.role)
                effective_tenant = get_settings().active_tenant
                history = await cls._load_agent_history(
                    db,
                    conversation_id,
                    exclude_message_id=chat_req.user_message_id,
                )
                # Các SELECT ở trên đã mở một transaction và giữ connection
                # trong pool. Trả connection về trước khi chờ Agent 15-35 giây;
                # nếu giữ nguyên, chỉ vài chat đồng thời là pool cạn và request
                # mới phải chờ tới pool timeout dù database vẫn hoạt động.
                await db.commit()

                if on_event is None:
                    agent_answer = await cls.agent_client.query_agent(
                        user_id=str(user_id),
                        query=question,
                        department=effective_department,
                        request_id=str(chat_request_id),
                        user_role=effective_role,
                        tenant_id=effective_tenant,
                        history=history,
                    )
                else:
                    agent_answer = None
                    async for event in cls.agent_client.stream_query_agent(
                        user_id=str(user_id),
                        query=question,
                        department=effective_department,
                        request_id=str(chat_request_id),
                        user_role=effective_role,
                        tenant_id=effective_tenant,
                        history=history,
                    ):
                        if event["type"] == "error":
                            raise AIAgentClientError(
                                "AGENT_SERVICE_ERROR",
                                str(event.get("message") or "AI Agent stream failed"),
                            )
                        await on_event(event)
                        if event["type"] == "done":
                            try:
                                agent_answer = AgentAnswerDTO.model_validate(event.get("answer"))
                            except (TypeError, ValueError) as exc:
                                raise AIAgentClientError(
                                    "AGENT_INVALID_RESPONSE",
                                    "AI Agent stream is missing the final answer",
                                    False,
                                ) from exc
                    if agent_answer is None:
                        raise AIAgentClientError(
                            "AGENT_INVALID_RESPONSE",
                            "AI Agent stream ended without a final answer",
                            True,
                        )
                mapped = AgentAnswerAdapter.map(agent_answer, chat_request_id)

                # Đính kèm public_url, document_id, version và effective_date từ DocumentDB vào từng citation
                if mapped.citations:
                    titles = [c["title"] for c in mapped.citations if c.get("title")]
                    source_files = [c["source_file"] for c in mapped.citations if c.get("source_file")]
                    stems = [os.path.splitext(sf)[0] for sf in source_files if sf]

                    conditions = []
                    if titles:
                        conditions.append(DocumentDB.title.in_(titles))
                    if source_files:
                        conditions.append(DocumentDB.source_file.in_(source_files))
                    for st in stems:
                        conditions.append(DocumentDB.source_file.like(f"{st}%"))
                        conditions.append(DocumentDB.title.like(f"{st}%"))

                    if conditions:
                        doc_res = await db.execute(
                            select(DocumentDB)
                            .where(
                                DocumentDB.tenant == get_settings().active_tenant,
                                or_(*conditions),
                            )
                            .order_by(
                                case((DocumentDB.status == "ACTIVE", 0), else_=1),
                                desc(DocumentDB.updated_at),
                            )
                        )
                        docs = doc_res.scalars().all()
                        doc_map: dict[str, DocumentDB] = {}
                        for d in docs:
                            if d.source_file and d.source_file.casefold() not in doc_map:
                                doc_map[d.source_file.casefold()] = d
                                doc_map[os.path.splitext(d.source_file)[0].casefold()] = d
                            if d.title and d.title.casefold() not in doc_map:
                                doc_map[d.title.casefold()] = d
                                doc_map[os.path.splitext(d.title)[0].casefold()] = d
                        for c in mapped.citations:
                            sf = (c.get("source_file") or "").casefold()
                            sf_stem = os.path.splitext(sf)[0] if sf else ""
                            tt = (c.get("title") or "").casefold()
                            tt_stem = os.path.splitext(tt)[0] if tt else ""
                            matched_doc = (
                                doc_map.get(sf)
                                or doc_map.get(sf_stem)
                                or doc_map.get(tt)
                                or doc_map.get(tt_stem)
                            )
                            if matched_doc:
                                c["public_url"] = matched_doc.public_url
                                c["document_id"] = str(matched_doc.id)
                                c["version"] = matched_doc.version or c.get("version")
                                c["effective_date"] = matched_doc.effective_date or c.get("effective_date")

                assistant_msg_id = uuid.uuid4()
                assistant_msg = MessageDB(
                    id=assistant_msg_id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=mapped.message_content,
                    chat_request_id=chat_request_id,
                    citations=mapped.citations,
                    confidence_score=agent_answer.confidence_score,
                    escalated=agent_answer.escalate,
                )
                db.add(assistant_msg)
                await db.flush()

                if agent_answer.escalate and AgentAnswerAdapter.blocks_workflow_creation(agent_answer):
                    # Boundary flow MVP-1 không có action nào tạo workflow; lượt
                    # chat này chỉ trả lời/hướng dẫn/chuẩn bị nội dung.
                    logger.info(
                        f"Skip ticket creation for {chat_request_id}: MVP-1 boundary flow does not create workflow "
                        f"records (scenario={agent_answer.boundary.scenario_id}, "
                        f"runtime_action={agent_answer.boundary.runtime_action})"
                    )
                elif agent_answer.escalate:
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
                chat_req.ticket_proposal = AgentAnswerAdapter.case_proposal(
                    agent_answer, get_settings().enable_create_case
                )
                chat_req.failure = None
                chat_req.retryable = mapped.retryable
                chat_req.assistant_message_id = assistant_msg_id
                chat_req.latency_ms = int((time.monotonic() - start_time) * 1000)
                await db.commit()
                if on_event is not None:
                    await on_event(
                        {
                            "type": "result",
                            "data": cls._status_payload(
                                chat_req, boundary=mapped.boundary, quick_prompts=mapped.quick_prompts
                            ),
                        }
                    )

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
                        if on_event is not None:
                            await on_event({"type": "result", "data": cls._status_payload(chat_req)})
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

        return cls._status_payload(chat_req)

    @classmethod
    async def confirm_ticket_proposal(
        cls,
        db: AsyncSession,
        chat_request_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Người hỏi xác nhận đề xuất CREATE_CASE -> tạo ticket, idempotent.

        Khoá hàng chat_request (FOR UPDATE) để hai lần bấm đồng thời không tạo
        hai ticket; lần bấm sau trả lại ticket đã tạo.
        """
        chat_req, proposal = await cls._locked_proposal(db, chat_request_id, user_id)
        if proposal.get("ticket_id"):
            return proposal
        if proposal.get("status") == "REJECTED":
            raise ConflictError(code="PROPOSAL_REJECTED", message="Đề xuất này đã bị từ chối; hãy gửi yêu cầu mới.")
        if not get_settings().enable_create_case:
            raise ForbiddenError("Tạo ticket từ hội thoại đang tắt.")

        ticket = await TicketService.create_from_agent_draft(
            db=db,
            draft=AgentTicketDraftDTO.model_validate(proposal["draft"]),
            conversation_id=chat_req.conversation_id,
            message_id=chat_req.assistant_message_id,
            requester_id=user_id,
        )
        if chat_req.assistant_message_id:
            msg = await db.get(MessageDB, chat_req.assistant_message_id)
            if msg:
                msg.ticket_id = ticket.id
        confirmed = {
            **proposal,
            "status": "CONFIRMED",
            "ticket_id": str(ticket.id),
            "ticket_code": ticket.ticket_code,
            "confirmed_at": datetime.now(UTC).isoformat(),
        }
        chat_req.ticket_proposal = confirmed  # gán dict mới để SQLAlchemy thấy thay đổi JSON
        db.add(cls._proposal_audit(user_id, "AGENT_CASE_CONFIRMED", chat_request_id, proposal, confirmed))
        await db.commit()
        logger.info(f"Ticket {ticket.ticket_code} created by user confirmation for chat_request {chat_request_id}")
        return confirmed

    @classmethod
    async def reject_ticket_proposal(
        cls,
        db: AsyncSession,
        chat_request_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Người hỏi từ chối đề xuất CREATE_CASE: không tạo ticket, ghi lý do + audit. Idempotent."""
        chat_req, proposal = await cls._locked_proposal(db, chat_request_id, user_id)
        if proposal.get("ticket_id"):
            raise ConflictError(code="PROPOSAL_ALREADY_CONFIRMED", message="Ticket đã được tạo, không thể từ chối.")
        if proposal.get("status") == "REJECTED":
            return proposal
        rejected = {
            **proposal,
            "status": "REJECTED",
            "rejection_reason": (reason or "").strip()[:500] or None,
            "rejected_at": datetime.now(UTC).isoformat(),
        }
        chat_req.ticket_proposal = rejected
        db.add(cls._proposal_audit(user_id, "AGENT_CASE_REJECTED", chat_request_id, proposal, rejected))
        await db.commit()
        logger.info(f"Ticket proposal rejected by user for chat_request {chat_request_id}")
        return rejected

    @staticmethod
    async def _locked_proposal(
        db: AsyncSession, chat_request_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[ChatRequestDB, dict[str, Any]]:
        """Khoá hàng chat_request (FOR UPDATE) để duyệt/từ chối đồng thời không giẫm nhau."""
        res = await db.execute(
            select(ChatRequestDB).where(ChatRequestDB.id == chat_request_id).with_for_update()
        )
        chat_req = res.scalar_one_or_none()
        if not chat_req:
            raise NotFoundError(code="CHAT_REQUEST_NOT_FOUND", message="Không tìm thấy yêu cầu chat.")
        if chat_req.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền xử lý yêu cầu này.")
        if not chat_req.ticket_proposal:
            raise ConflictError(code="NO_TICKET_PROPOSAL", message="Yêu cầu này không có đề xuất tạo ticket.")
        return chat_req, chat_req.ticket_proposal

    @staticmethod
    def _proposal_audit(
        actor_id: uuid.UUID, action: str, chat_request_id: uuid.UUID, before: dict, after: dict
    ) -> AuditLogDB:
        keep = ("status", "ticket_code", "rejection_reason")
        return AuditLogDB(
            tenant=get_settings().active_tenant,
            actor_id=actor_id,
            action=action,
            resource_type="chat_request.ticket_proposal",
            resource_id=str(chat_request_id),
            before_state={k: before.get(k) for k in keep},
            after_state={k: after.get(k) for k in keep},
        )

    @staticmethod
    def _status_payload(
        chat_req: ChatRequestDB,
        boundary: dict[str, Any] | None = None,
        quick_prompts: list[str] | None = None,
    ) -> dict[str, Any]:
        """`boundary` và `quick_prompts` được truyền vào thay vì đọc từ DB."""
        return {
            "boundary": boundary,
            "quick_prompts": quick_prompts,
            "chat_request_id": str(chat_req.id),
            "conversation_id": str(chat_req.conversation_id),
            "user_message_id": str(chat_req.user_message_id) if chat_req.user_message_id else None,
            "assistant_message_id": str(chat_req.assistant_message_id) if chat_req.assistant_message_id else None,
            "state": chat_req.state,
            "answer_status": chat_req.answer_status,
            "answer": chat_req.answer,
            "citations": sanitize_citations_for_client(chat_req.citations),
            "warnings": chat_req.warnings or [],
            "clarification": chat_req.clarification,
            "failure": chat_req.failure,
            "latency_ms": chat_req.latency_ms,
            "ticket_proposal": chat_req.ticket_proposal,
        }

    @classmethod
    async def stream_chat_request(
        cls,
        chat_request_id: uuid.UUID,
        user_id: uuid.UUID,
        department: str,
        question: str,
        conversation_id: uuid.UUID,
    ) -> AsyncIterator[dict[str, Any]]:
        """Chạy request và chuyển tiếp event; task vẫn persist kết quả nếu client ngắt kết nối."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def run() -> None:
            try:
                await cls._process_chat_rag_request(
                    chat_request_id=chat_request_id,
                    user_id=user_id,
                    department=department,
                    question=question,
                    conversation_id=conversation_id,
                    on_event=queue.put,
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=cls.stream_heartbeat_seconds)
                except TimeoutError:
                    yield {"type": "heartbeat"}
                    continue
                if event is None:
                    break
                yield event
        finally:
            # Không cancel công việc khi tab/browser ngắt SSE: câu trả lời vẫn
            # phải được lưu để người dùng tải lại lịch sử hoặc poll tiếp.
            if task.done():
                await task

    @classmethod
    async def _process_direct_stream_rag_request(
        cls,
        chat_request_id: uuid.UUID,
        user_message_id: uuid.UUID,
        user_id: uuid.UUID,
        department: str,
        question: str,
        conversation_id: uuid.UUID,
        on_event: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        start_time = time.monotonic()
        clean_question = question.strip() if question else ""
        if not clean_question:
            raise AppException(
                status_code=400,
                code="VALIDATION_ERROR",
                message="Câu hỏi không được để trống.",
            )

        factory = cls.session_factory or AsyncSessionLocal
        # 1. Gộp toàn bộ xác thực, load history và tạo Message/ChatRequest trong 1 Transaction duy nhất
        async with factory() as db:
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
            if conv.title == DEFAULT_CONVERSATION_TITLE:
                conv.title = make_conversation_title(clean_question)
            conv.updated_at = datetime.now(UTC)

            profile = await db.get(ProfileDB, user_id)
            if profile is None:
                raise AIAgentClientError("IDENTITY_PROFILE_MISSING", "Authenticated profile no longer exists", False)
            if not str(profile.department or "").strip() or not str(profile.role or "").strip():
                raise AIAgentClientError("IDENTITY_PROFILE_INCOMPLETE", "Profile role/department is incomplete", False)
            effective_department = str(profile.department).upper().strip()
            effective_role = _agent_role(profile.role)
            effective_tenant = get_settings().active_tenant

            history = await cls._load_agent_history(db, conversation_id)

            user_msg = MessageDB(
                id=user_message_id,
                conversation_id=conversation_id,
                role="user",
                content=clean_question,
            )
            chat_req = ChatRequestDB(
                id=chat_request_id,
                conversation_id=conversation_id,
                user_id=user_id,
                question=clean_question,
                state="GENERATING",
            )
            db.add_all([user_msg, chat_req])
            await db.flush()

            chat_req.user_message_id = user_message_id
            user_msg.chat_request_id = chat_request_id
            await db.commit()

        # 2. Gọi Agent SSE stream ngay lập tức (Không giữ DB connection)
        try:
            agent_answer = None
            async for event in cls.agent_client.stream_query_agent(
                user_id=str(user_id),
                query=clean_question,
                department=effective_department,
                request_id=str(chat_request_id),
                user_role=effective_role,
                tenant_id=effective_tenant,
                history=history,
            ):
                if event["type"] == "error":
                    raise AIAgentClientError(
                        "AGENT_SERVICE_ERROR",
                        str(event.get("message") or "AI Agent stream failed"),
                    )
                await on_event(event)
                if event["type"] == "done":
                    try:
                        agent_answer = AgentAnswerDTO.model_validate(event.get("answer"))
                    except (TypeError, ValueError) as exc:
                        raise AIAgentClientError(
                            "AGENT_INVALID_RESPONSE",
                            "AI Agent stream is missing the final answer",
                            False,
                        ) from exc
            if agent_answer is None:
                raise AIAgentClientError(
                    "AGENT_INVALID_RESPONSE",
                    "AI Agent stream ended without a final answer",
                    True,
                )

            mapped = AgentAnswerAdapter.map(agent_answer, chat_request_id)

            # 3. Ghi nhận kết quả trả lời vào DB
            async with factory() as db:
                if mapped.citations:
                    titles = [c["title"] for c in mapped.citations if c.get("title")]
                    source_files = [c["source_file"] for c in mapped.citations if c.get("source_file")]
                    stems = [os.path.splitext(sf)[0] for sf in source_files if sf]

                    conditions = []
                    if titles:
                        conditions.append(DocumentDB.title.in_(titles))
                    if source_files:
                        conditions.append(DocumentDB.source_file.in_(source_files))
                    for st in stems:
                        conditions.append(DocumentDB.source_file.like(f"{st}%"))
                        conditions.append(DocumentDB.title.like(f"{st}%"))

                    if conditions:
                        doc_res = await db.execute(
                            select(DocumentDB)
                            .where(
                                DocumentDB.tenant == get_settings().active_tenant,
                                or_(*conditions),
                            )
                            .order_by(
                                case((DocumentDB.status == "ACTIVE", 0), else_=1),
                                desc(DocumentDB.updated_at),
                            )
                        )
                        docs = doc_res.scalars().all()
                        doc_map: dict[str, DocumentDB] = {}
                        for d in docs:
                            if d.source_file and d.source_file.casefold() not in doc_map:
                                doc_map[d.source_file.casefold()] = d
                                doc_map[os.path.splitext(d.source_file)[0].casefold()] = d
                            if d.title and d.title.casefold() not in doc_map:
                                doc_map[d.title.casefold()] = d
                                doc_map[os.path.splitext(d.title)[0].casefold()] = d
                        for c in mapped.citations:
                            sf = (c.get("source_file") or "").casefold()
                            sf_stem = os.path.splitext(sf)[0] if sf else ""
                            tt = (c.get("title") or "").casefold()
                            tt_stem = os.path.splitext(tt)[0] if tt else ""
                            matched_doc = (
                                doc_map.get(sf)
                                or doc_map.get(sf_stem)
                                or doc_map.get(tt)
                                or doc_map.get(tt_stem)
                            )
                            if matched_doc:
                                c["public_url"] = matched_doc.public_url
                                c["document_id"] = str(matched_doc.id)
                                c["version"] = matched_doc.version or c.get("version")
                                c["effective_date"] = matched_doc.effective_date or c.get("effective_date")

                assistant_msg_id = uuid.uuid4()
                assistant_msg = MessageDB(
                    id=assistant_msg_id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=mapped.message_content,
                    chat_request_id=chat_request_id,
                    citations=mapped.citations,
                    confidence_score=agent_answer.confidence_score,
                    escalated=agent_answer.escalate,
                )
                db.add(assistant_msg)
                await db.flush()

                if agent_answer.escalate and AgentAnswerAdapter.blocks_workflow_creation(agent_answer):
                    logger.info(
                        f"Skip ticket creation for {chat_request_id}: MVP-1 boundary flow does not create workflow "
                        f"records (scenario={agent_answer.boundary.scenario_id}, "
                        f"runtime_action={agent_answer.boundary.runtime_action})"
                    )
                elif agent_answer.escalate:
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

                chat_req = await db.get(ChatRequestDB, chat_request_id)
                if chat_req:
                    chat_req.state = mapped.state
                    chat_req.answer_status = mapped.answer_status
                    chat_req.answer = mapped.answer
                    chat_req.citations = mapped.citations
                    chat_req.warnings = mapped.warnings
                    chat_req.clarification = mapped.clarification
                    chat_req.ticket_proposal = AgentAnswerAdapter.case_proposal(
                        agent_answer, get_settings().enable_create_case
                    )
                    chat_req.failure = None
                    chat_req.retryable = mapped.retryable
                    chat_req.assistant_message_id = assistant_msg_id
                    chat_req.latency_ms = int((time.monotonic() - start_time) * 1000)
                    await db.commit()
                    await on_event(
                        {
                            "type": "result",
                            "data": cls._status_payload(
                                chat_req, boundary=mapped.boundary, quick_prompts=mapped.quick_prompts
                            ),
                        }
                    )

        except Exception as exc:
            logger.error(f"Error streaming Chat RAG request {chat_request_id}: {exc}", exc_info=True)
            try:
                async with factory() as db:
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
                        await on_event({"type": "result", "data": cls._status_payload(chat_req)})
            except Exception as inner_exc:
                logger.error(f"Failed to record FAILED state for stream {chat_request_id}: {inner_exc}")
            raise

    @classmethod
    async def stream_new_chat_request(
        cls,
        chat_request_id: uuid.UUID,
        user_message_id: uuid.UUID,
        user_id: uuid.UUID,
        department: str,
        question: str,
        conversation_id: uuid.UUID,
    ) -> AsyncIterator[dict[str, Any]]:
        """Lưu request rồi chạy Agent trong task độc lập với kết nối SSE.

        Route có thể phát event tiếp nhận ngay trước khi Supabase hoàn tất các
        lệnh ghi. Nếu browser ngắt kết nối, task vẫn tiếp tục lưu và xử lý để
        người dùng có thể tải lại lịch sử sau đó.
        """
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def run() -> None:
            try:
                await cls._process_direct_stream_rag_request(
                    chat_request_id=chat_request_id,
                    user_message_id=user_message_id,
                    user_id=user_id,
                    department=department,
                    question=question,
                    conversation_id=conversation_id,
                    on_event=queue.put,
                )
            except AppException as exc:
                await queue.put(
                    {
                        "type": "error",
                        "code": exc.code,
                        "message": exc.message,
                        "status": exc.status_code,
                        "retryable": exc.retryable,
                    }
                )
            except (SQLAlchemyError, ConnectionError, TimeoutError, socket.gaierror) as exc:
                logger.error(f"Database unavailable while creating chat request: {exc}", exc_info=True)
                await queue.put(
                    {
                        "type": "error",
                        "code": "DATABASE_UNAVAILABLE",
                        "message": "Backend không thể kết nối cơ sở dữ liệu. Vui lòng thử lại sau.",
                        "status": 503,
                        "retryable": True,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - lỗi phải được chuyển thành event SSE có cấu trúc
                logger.error(f"Failed to initialize chat request: {exc}", exc_info=True)
                await queue.put(
                    {
                        "type": "error",
                        "code": "CHAT_REQUEST_INIT_FAILED",
                        "message": "Không thể tiếp nhận câu hỏi lúc này. Vui lòng thử lại.",
                        "status": 500,
                        "retryable": True,
                    }
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=cls.stream_heartbeat_seconds)
                except TimeoutError:
                    yield {"type": "heartbeat"}
                    continue
                if event is None:
                    break
                yield event
        finally:
            if task.done():
                await task

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
            cls._schedule_chat_request(
                chat_request_id=new_chat_req_id,
                user_id=user_id,
                department=department,
                question=chat_req.question,
                conversation_id=chat_req.conversation_id,
            )

        return {
            "chat_request_id": str(new_chat_req_id),
            "parent_chat_request_id": str(chat_request_id),
            "state": "QUEUED",
            "poll_after_ms": 1000,
        }

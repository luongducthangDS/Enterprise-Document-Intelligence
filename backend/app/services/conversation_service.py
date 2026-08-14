import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.messages import MessageDB
from app.services.content_safety import sanitize_citations_for_client


class ConversationService:
    @staticmethod
    def title_from_question(question: str) -> str:
        normalized = " ".join(question.split())
        if len(normalized) <= 48:
            return normalized
        shortened = normalized[:48].rsplit(" ", 1)[0].rstrip(".,!?;:")
        return f"{shortened}..."

    @classmethod
    async def rename_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
    ) -> dict:
        stmt = select(ConversationDB).where(ConversationDB.id == conversation_id)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if not conversation or conversation.state == "DELETED":
            raise NotFoundError(code="CONVERSATION_NOT_FOUND", message="Không tìm thấy cuộc hội thoại")
        if conversation.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền cập nhật cuộc hội thoại này")

        clean_title = " ".join(title.split())
        conversation.title = clean_title
        await db.commit()
        await db.refresh(conversation)

        return {
            "conversation_id": str(conversation.id),
            "title": conversation.title,
            "state": conversation.state,
        }

    @classmethod
    async def list_conversations(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[dict]:
        stmt = (
            select(ConversationDB)
            .where(
                ConversationDB.user_id == user_id,
                ConversationDB.state != "DELETED",
            )
            .order_by(ConversationDB.updated_at.desc(), ConversationDB.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        conversations = list(result.scalars().all())
        if not conversations:
            return []

        conversation_ids = [conversation.id for conversation in conversations]
        message_stmt = (
            select(
                MessageDB.conversation_id,
                func.count(MessageDB.id),
                func.max(MessageDB.created_at),
            )
            .where(MessageDB.conversation_id.in_(conversation_ids))
            .group_by(MessageDB.conversation_id)
        )
        message_result = await db.execute(message_stmt)
        message_stats = {
            conversation_id: (message_count, last_message_at)
            for conversation_id, message_count, last_message_at in message_result.all()
        }
        question_stmt = (
            select(MessageDB.conversation_id, MessageDB.content)
            .where(
                MessageDB.conversation_id.in_(conversation_ids),
                func.lower(MessageDB.role) == "user",
            )
            .order_by(MessageDB.created_at.asc(), MessageDB.id.asc())
        )
        question_result = await db.execute(question_stmt)
        first_questions = {}
        for conversation_id, content in question_result.all():
            first_questions.setdefault(conversation_id, content)

        items = []
        for conversation in conversations:
            message_count, last_message_at = message_stats.get(conversation.id, (0, None))
            title = conversation.title
            if title == "Hội thoại mới" and first_questions.get(conversation.id):
                title = cls.title_from_question(first_questions[conversation.id])
            items.append(
                {
                    "conversation_id": str(conversation.id),
                    "title": title,
                    "state": conversation.state,
                    "created_at": conversation.created_at.isoformat(),
                    "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
                    "message_count": message_count or 0,
                    "last_message_at": last_message_at.isoformat() if last_message_at else None,
                }
            )

        return sorted(
            items,
            key=lambda item: item["last_message_at"] or item["created_at"],
            reverse=True,
        )

    @classmethod
    async def create_conversation(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        title: str | None = None,
    ) -> dict:
        clean_title = title.strip() if title and title.strip() else "Hội thoại mới"
        conv_id = uuid.uuid4()

        new_conv = ConversationDB(
            id=conv_id,
            user_id=user_id,
            title=clean_title,
            state="ACTIVE",
        )
        db.add(new_conv)
        await db.commit()
        await db.refresh(new_conv)

        return {
            "conversation_id": str(new_conv.id),
            "state": new_conv.state,
            "title": new_conv.title,
            "created_at": new_conv.created_at.isoformat(),
        }

    @classmethod
    async def get_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        stmt = select(ConversationDB).where(ConversationDB.id == conversation_id)
        result = await db.execute(stmt)
        conv = result.scalar_one_or_none()

        if not conv or conv.state == "DELETED":
            raise NotFoundError(
                code="CONVERSATION_NOT_FOUND",
                message="Không tìm thấy cuộc hội thoại",
            )

        if conv.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền truy cập cuộc hội thoại này")

        # Count messages and last message timestamp
        msg_stmt = select(
            func.count(MessageDB.id),
            func.max(MessageDB.created_at),
        ).where(MessageDB.conversation_id == conversation_id)
        msg_res = await db.execute(msg_stmt)
        msg_count, last_msg_at = msg_res.one()

        return {
            "conversation_id": str(conv.id),
            "title": conv.title,
            "state": conv.state,
            "created_at": conv.created_at.isoformat(),
            "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
            "message_count": msg_count or 0,
            "last_message_at": last_msg_at.isoformat() if last_msg_at else None,
        }

    @classmethod
    async def get_conversation_messages(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict:
        # Check conversation existence and ownership
        stmt = select(ConversationDB).where(ConversationDB.id == conversation_id)
        result = await db.execute(stmt)
        conv = result.scalar_one_or_none()

        if not conv or conv.state == "DELETED":
            raise NotFoundError(
                code="CONVERSATION_NOT_FOUND",
                message="Không tìm thấy cuộc hội thoại",
            )

        if conv.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền truy cập cuộc hội thoại này")

        msg_query = (
            select(MessageDB, ChatRequestDB.answer_status)
            .outerjoin(ChatRequestDB, ChatRequestDB.id == MessageDB.chat_request_id)
            .where(MessageDB.conversation_id == conversation_id)
        )

        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
                msg_query = msg_query.where(MessageDB.created_at > cursor_dt)
            except ValueError:
                pass

        msg_query = msg_query.order_by(MessageDB.created_at.asc()).limit(limit + 1)
        msg_res = await db.execute(msg_query)
        fetched_messages = list(msg_res.all())

        has_more = len(fetched_messages) > limit
        result_messages = fetched_messages[:limit]
        next_cursor = result_messages[-1][0].created_at.isoformat() if has_more and result_messages else None

        message_items = [
            {
                "message_id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "chat_request_id": str(msg.chat_request_id) if msg.chat_request_id else None,
                "answer_status": answer_status,
                "citations": sanitize_citations_for_client(msg.citations),
                "created_at": msg.created_at.isoformat(),
            }
            for msg, answer_status in result_messages
        ]

        return {
            "conversation_id": str(conversation_id),
            "messages": message_items,
            "pagination": {
                "limit": limit,
                "next_cursor": next_cursor,
            },
        }

    @classmethod
    async def end_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        stmt = select(ConversationDB).where(ConversationDB.id == conversation_id)
        result = await db.execute(stmt)
        conv = result.scalar_one_or_none()

        if not conv or conv.state == "DELETED":
            raise NotFoundError(
                code="CONVERSATION_NOT_FOUND",
                message="Không tìm thấy cuộc hội thoại",
            )

        if conv.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền thao tác trên cuộc hội thoại này")

        if conv.state == "ENDED":
            raise ConflictError(
                code="CONVERSATION_ENDED",
                message="Phiên hội thoại đã kết thúc trước đó",
            )

        conv.state = "ENDED"
        conv.ended_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(conv)

        return {
            "conversation_id": str(conv.id),
            "state": "ENDED",
            "ended_at": conv.ended_at.isoformat() if conv.ended_at else datetime.now(UTC).isoformat(),
        }

    @classmethod
    async def delete_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        stmt = select(ConversationDB).where(ConversationDB.id == conversation_id)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if not conversation or conversation.state == "DELETED":
            raise NotFoundError(code="CONVERSATION_NOT_FOUND", message="Không tìm thấy cuộc hội thoại")
        if conversation.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền xóa cuộc hội thoại này")

        now = datetime.now(UTC)
        conversation.state = "DELETED"
        conversation.ended_at = conversation.ended_at or now
        conversation.updated_at = now
        await db.commit()

        return {"conversation_id": str(conversation.id), "deleted": True}

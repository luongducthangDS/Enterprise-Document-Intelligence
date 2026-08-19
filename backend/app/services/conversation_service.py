import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.messages import MessageDB
from app.services.content_safety import sanitize_citations_for_client

DEFAULT_CONVERSATION_TITLE = "Hội thoại mới"
MAX_CONVERSATION_TITLE_LENGTH = 72


def make_conversation_title(question: str) -> str:
    clean_question = " ".join(question.split())
    if len(clean_question) <= MAX_CONVERSATION_TITLE_LENGTH:
        return clean_question
    return f"{clean_question[: MAX_CONVERSATION_TITLE_LENGTH - 1].rstrip()}…"


class ConversationService:
    @classmethod
    async def rename_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
    ) -> dict:
        result = await db.execute(select(ConversationDB).where(ConversationDB.id == conversation_id))
        conversation = result.scalar_one_or_none()
        if not conversation or conversation.state == "DELETED":
            raise NotFoundError(code="CONVERSATION_NOT_FOUND", message="Không tìm thấy cuộc hội thoại")
        if conversation.user_id != user_id:
            raise ForbiddenError("Bạn không có quyền cập nhật cuộc hội thoại này")

        conversation.title = " ".join(title.split())
        conversation.updated_at = datetime.now(UTC)
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
        message_stats = (
            select(
                MessageDB.conversation_id.label("conversation_id"),
                func.count(MessageDB.id).label("message_count"),
                func.max(MessageDB.created_at).label("last_message_at"),
            )
            .group_by(MessageDB.conversation_id)
            .subquery()
        )
        first_user_message = (
            select(MessageDB.content)
            .where(
                MessageDB.conversation_id == ConversationDB.id,
                func.lower(MessageDB.role) == "user",
            )
            .order_by(MessageDB.created_at.asc(), MessageDB.id.asc())
            .limit(1)
            .correlate(ConversationDB)
            .scalar_subquery()
        )
        stmt = (
            select(
                ConversationDB,
                func.coalesce(message_stats.c.message_count, 0),
                message_stats.c.last_message_at,
                first_user_message,
            )
            .outerjoin(message_stats, message_stats.c.conversation_id == ConversationDB.id)
            .where(
                ConversationDB.user_id == user_id,
                ConversationDB.state != "DELETED",
            )
            .order_by(func.coalesce(message_stats.c.last_message_at, ConversationDB.updated_at).desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "conversation_id": str(conversation.id),
                "title": (
                    make_conversation_title(first_question)
                    if conversation.title == DEFAULT_CONVERSATION_TITLE and first_question
                    else conversation.title
                ),
                "state": conversation.state,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
                "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
                "message_count": message_count,
                "last_message_at": last_message_at.isoformat() if last_message_at else None,
            }
            for conversation, message_count, last_message_at, first_question in rows
        ]

    @classmethod
    async def create_conversation(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        title: str | None = None,
    ) -> dict:
        clean_title = title.strip() if title and title.strip() else DEFAULT_CONVERSATION_TITLE
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
            "updated_at": conv.updated_at.isoformat(),
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

        msg_query = msg_query.order_by(MessageDB.created_at.asc(), MessageDB.id.asc()).limit(limit + 1)
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
        result = await db.execute(select(ConversationDB).where(ConversationDB.id == conversation_id))
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

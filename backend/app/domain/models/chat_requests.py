import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.models.conversations import ConversationDB
    from app.domain.models.messages import MessageDB
    from app.domain.models.profile import ProfileDB


class ChatRequestDB(Base):
    __tablename__ = "chat_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    state: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="QUEUED",
    )

    answer_status: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    citations: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    warnings: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    clarification: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    failure: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Đề xuất CREATE_CASE chờ người hỏi xác nhận (migration 0014).
    ticket_proposal: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    user_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "messages.id",
            ondelete="SET NULL",
            use_alter=True,
            name="chat_requests_user_message_id_fkey",
        ),
        nullable=True,
    )

    assistant_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "messages.id",
            ondelete="SET NULL",
            use_alter=True,
            name="chat_requests_assistant_message_id_fkey",
        ),
        nullable=True,
    )

    parent_chat_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    retryable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    conversation: Mapped["ConversationDB"] = relationship("ConversationDB")
    user: Mapped["ProfileDB"] = relationship("ProfileDB")
    user_message: Mapped["MessageDB | None"] = relationship("MessageDB", foreign_keys=[user_message_id])
    assistant_message: Mapped["MessageDB | None"] = relationship("MessageDB", foreign_keys=[assistant_message_id])

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.models.chat_requests import ChatRequestDB
    from app.domain.models.conversations import ConversationDB
    from app.domain.models.ticket import TicketDB


class MessageDB(Base):
    __tablename__ = "messages"

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

    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    chat_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "chat_requests.id",
            ondelete="SET NULL",
            use_alter=True,
            name="messages_chat_request_id_fkey",
        ),
        nullable=True,
    )

    answer_status: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    citations: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    confidence_score: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    escalated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "tickets.id",
            ondelete="SET NULL",
            use_alter=True,
            name="messages_ticket_id_fkey",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    conversation: Mapped["ConversationDB"] = relationship(
        "ConversationDB",
        back_populates="messages",
    )

    chat_request: Mapped["ChatRequestDB | None"] = relationship(
        "ChatRequestDB",
        foreign_keys=[chat_request_id],
    )

    ticket: Mapped["TicketDB | None"] = relationship(
        "TicketDB",
        foreign_keys=[ticket_id],
    )

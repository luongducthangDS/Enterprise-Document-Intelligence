import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.models.conversations import ConversationDB
    from app.domain.models.messages import MessageDB
    from app.domain.models.profile import ProfileDB


class TicketDB(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    ticket_code: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE", use_alter=True, name="tickets_message_id_fkey"),
        nullable=False,
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    employee_question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    escalate_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    confidence_score: Mapped[float] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    target_department: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="MEDIUM",
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="OPEN",
    )

    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id"),
        nullable=True,
    )

    resolution_note: Mapped[str | None] = mapped_column(
        Text,
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

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    requester: Mapped["ProfileDB"] = relationship(
        "ProfileDB",
        foreign_keys=[requester_id],
    )

    assignee: Mapped["ProfileDB | None"] = relationship(
        "ProfileDB",
        foreign_keys=[assignee_id],
    )

    conversation: Mapped["ConversationDB"] = relationship(
        "ConversationDB",
        back_populates="tickets",
    )

    message: Mapped["MessageDB"] = relationship(
        "MessageDB",
        foreign_keys=[message_id],
    )

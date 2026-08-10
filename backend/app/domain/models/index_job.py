import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.models.profile import ProfileDB


class IndexJobDB(Base):
    __tablename__ = "index_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    document_ids: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    strategy: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="REPLACE",
    )

    state: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="QUEUED",
    )

    stage: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="QUEUED",
    )

    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    active_index_version: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="v1.0",
    )

    error: Mapped[str | None] = mapped_column(
        String,
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
    requester: Mapped["ProfileDB"] = relationship(
        "ProfileDB",
    )

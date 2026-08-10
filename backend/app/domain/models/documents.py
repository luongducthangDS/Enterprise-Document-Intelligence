import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.models.profile import ProfileDB


class DocumentDB(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    title: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="Tài liệu không tên",
    )

    source_file: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="GENERAL",
    )

    version: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    effective_date: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    confidentiality: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="INTERNAL",
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="ACTIVE",
    )

    source_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="FILE_UPLOAD",
    )

    is_official_policy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    caveat: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    processed_path: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    chunks_path: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    chroma_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
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
    uploader: Mapped["ProfileDB"] = relationship(
        "ProfileDB",
    )
    ingestion_jobs: Mapped[list["IngestionJobDB"]] = relationship(
        "IngestionJobDB",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class IngestionJobDB(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    state: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="QUEUED",
    )

    stage: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="UPLOADED",
    )

    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
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
    document: Mapped["DocumentDB"] = relationship(
        "DocumentDB",
        back_populates="ingestion_jobs",
    )


import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.models.profile import ProfileDB


class DocumentDB(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("tenant", "source_file", name="uq_documents_tenant_source_file"),)

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
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    file_content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    category: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="GENERAL",
    )

    tenant: Mapped[str] = mapped_column(String, nullable=False, default="nexatech")
    department: Mapped[str] = mapped_column(String, nullable=False, default="HR")
    access_scope: Mapped[str] = mapped_column(String, nullable=False, default="RESTRICTED")
    authorized_role: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    authorization_source: Mapped[str] = mapped_column(String, nullable=False, default="RUNTIME_UPLOAD")
    authority: Mapped[str] = mapped_column(String, nullable=False, default="tenant_official_policy")
    provenance: Mapped[str] = mapped_column(String, nullable=False, default="customer_provided")

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

    public_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    chroma_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
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
    uploader: Mapped["ProfileDB | None"] = relationship(
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



class DocumentSubmissionDB(Base):
    """Durable quarantine record for an uploaded document awaiting approval."""

    __tablename__ = "document_submissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    file_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, default="GENERAL")
    department: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String, nullable=True)
    confidentiality: Mapped[str] = mapped_column(String, nullable=False, default="INTERNAL")
    access_scope: Mapped[str] = mapped_column(String, nullable=False, default="RESTRICTED")
    authorized_role: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ANALYZING", index=True)
    stage: Mapped[str] = mapped_column(String, nullable=False, default="UPLOADED")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extract_method: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analysis_warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    publication_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True
    )
    public_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

"""SQLAlchemy 2.0 ORM Models for Enterprise Structured Knowledge System.

Bao gồm 6 bảng cốt lõi và 1 bảng Tenant quản lý định danh:
1. TENANTS (Bảng định danh tổ chức / doanh nghiệp)
2. DOCUMENTS (Hồ sơ tài liệu nghiệp vụ)
3. DOCUMENT_VERSIONS (Lịch sử phiên bản & SHA256 content hash bất biến)
4. CHUNK_RECORDS (Đoạn trích phân đoạn ngữ nghĩa)
5. KNOWLEDGE_ITEMS (6 loại tri thức có cấu trúc: DECISION, POLICY_RULE, ACTION_ITEM, RESPONSIBILITY, EXCEPTION, REQUIREMENT)
6. KNOWLEDGE_RELATIONS (5 loại quan hệ tri thức: SUPERSEDES, MODIFIES, IMPLEMENTS, CONFLICTS_WITH, REFERENCES)
7. EVIDENCE_RECORDS (Bằng chứng trích xuất nguyên văn kèm chỉ mục ký tự & SHA256 quote hash)

BẢO MẬT MULTI-TENANT:
Áp dụng Composite Foreign Keys (tenant_id + entity_id) ở cấp độ Database Engine để
ngăn chặn tuyệt đối việc liên kết hoặc tham chiếu chéo giữa các tenant.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class AuthorityLevel(str, enum.Enum):
    """Mô hình phân cấp thẩm quyền văn bản (Precedence Hierarchy)."""
    LEGAL = "LEGAL"                      # Rank 1: Luật, Nghị định, Thông tư
    BOARD_DECISION = "BOARD_DECISION"    # Rank 2: Quyết định Ban Giám đốc / Tổng Giám đốc
    COMPANY_POLICY = "COMPANY_POLICY"    # Rank 3: Quy chế / Chính sách chung toàn công ty
    DEPARTMENT_POLICY = "DEPARTMENT_POLICY" # Rank 4: Chính sách / Quy định riêng của khối
    SOP = "SOP"                          # Rank 5: Quy trình tác nghiệp chuẩn
    MEETING_MINUTES = "MEETING_MINUTES"  # Rank 6: Biên bản họp giao ban / rà soát


class KnowledgeType(str, enum.Enum):
    """6 loại tri thức có cấu trúc chuẩn hóa cho Phase P1."""
    DECISION = "DECISION"
    POLICY_RULE = "POLICY_RULE"
    ACTION_ITEM = "ACTION_ITEM"
    RESPONSIBILITY = "RESPONSIBILITY"
    EXCEPTION = "EXCEPTION"
    REQUIREMENT = "REQUIREMENT"


class RelationType(str, enum.Enum):
    """5 loại quan hệ tri thức chuẩn hóa giữa các Knowledge Items."""
    SUPERSEDES = "SUPERSEDES"
    MODIFIES = "MODIFIES"
    IMPLEMENTS = "IMPLEMENTS"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    REFERENCES = "REFERENCES"


class ScopeRelationType(str, enum.Enum):
    """Mô hình phân tích quan hệ phạm vi (Scope Reasoning)."""
    SAME = "SAME"
    SUBSET = "SUBSET"
    OVERLAP = "OVERLAP"
    DISJOINT = "DISJOINT"


class ReviewStatus(str, enum.Enum):
    """Vòng đời phê duyệt Human-In-The-Loop."""
    CANDIDATE = "CANDIDATE"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    # Legacy aliases
    AUTO_EXTRACTED = "AUTO_EXTRACTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    CORRECTED = "CORRECTED"


class Tenant(Base):
    """Bảng quản trị Tenant / Doanh nghiệp khách hàng."""
    __tablename__ = "tenants"

    tenant_id = Column(String(64), primary_key=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")


class Document(Base):
    """Bảng lưu trữ thông tin tài liệu nghiệp vụ."""
    __tablename__ = "documents"

    document_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    document_code = Column(String(64), nullable=False)
    title = Column(Text, nullable=False)
    document_domain = Column(String(64), nullable=False)  # COMPANY_POLICY | LEGAL | DEPARTMENT_PROCESS...
    authority_level = Column(String(32), default=AuthorityLevel.COMPANY_POLICY.value, nullable=False)
    access_scope = Column(String(32), default="COMPANY_WIDE", nullable=False)
    owner_department = Column(String(64), default="GENERAL", nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    tenant = relationship("Tenant", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "document_code", name="uq_tenant_doc_code"),
        UniqueConstraint("tenant_id", "document_id", name="uq_tenant_doc_id"),
        Index("idx_doc_tenant_dept", "tenant_id", "owner_department"),
        Index("idx_doc_tenant_domain", "tenant_id", "document_domain"),
    )


class DocumentVersion(Base):
    """Bảng lưu trữ phiên bản tài liệu kèm content hash bất biến."""
    __tablename__ = "document_versions"

    version_id = Column(String(64), primary_key=True)
    document_id = Column(String(64), nullable=False)
    tenant_id = Column(String(64), nullable=False)
    version_number = Column(String(32), default="1.0", nullable=False)
    raw_content_hash = Column(String(64), nullable=False)  # SHA256 của toàn văn chuẩn hóa
    effective_date_ymd = Column(Integer, default=1, nullable=False)
    expiry_date_ymd = Column(Integer, default=99991231, nullable=False)
    referenced_document_codes = Column(JSON, default=list, nullable=False)
    version_source = Column(String(64), default="OFFICIAL", nullable=False)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("Document", back_populates="versions")
    chunks = relationship("ChunkRecord", back_populates="version", cascade="all, delete-orphan")
    knowledge_items = relationship("KnowledgeItem", back_populates="version", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.document_id"],
            ondelete="CASCADE",
            name="fk_version_tenant_document",
        ),
        UniqueConstraint("tenant_id", "document_id", "version_number", name="uq_tenant_doc_ver"),
        UniqueConstraint("tenant_id", "version_id", name="uq_tenant_version_id"),
        Index("idx_version_dates", "tenant_id", "effective_date_ymd", "expiry_date_ymd"),
    )


class ChunkRecord(Base):
    """Bảng lưu trữ các chunk phân đoạn văn bản."""
    __tablename__ = "chunk_records"

    chunk_id = Column(String(128), primary_key=True)  # Format: {tenant}:{doc_id}:{ver_id}:{chunk_idx:04d}
    version_id = Column(String(64), nullable=False)
    tenant_id = Column(String(64), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    heading_path = Column(Text, default="", nullable=False)
    chunk_text = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)

    version = relationship("DocumentVersion", back_populates="chunks")
    evidence_records = relationship("EvidenceRecord", back_populates="chunk", cascade="all, delete-orphan", overlaps="knowledge_item,evidence_records")

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.version_id"],
            ondelete="CASCADE",
            name="fk_chunk_tenant_version",
        ),
        UniqueConstraint("tenant_id", "chunk_id", name="uq_tenant_chunk_id"),
        Index("idx_chunk_lookup", "tenant_id", "version_id", "chunk_index"),
    )


class KnowledgeItem(Base):
    """Bảng lưu trữ tri thức có cấu trúc chuẩn hóa cho Phase P1."""
    __tablename__ = "knowledge_items"

    knowledge_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    version_id = Column(String(64), nullable=False)
    item_type = Column(String(32), nullable=False)  # DECISION | POLICY_RULE | ACTION_ITEM...
    
    # First-class reasoning columns
    subject = Column(String(128), nullable=True, index=True)
    predicate = Column(String(128), nullable=True, index=True)
    object_value = Column(String(255), nullable=True)
    value_numeric = Column(Float, nullable=True)
    currency = Column(String(16), default="VND", nullable=True)
    scope = Column(JSON, default=list, nullable=False)
    effective_from_ymd = Column(Integer, default=1, nullable=False)
    effective_to_ymd = Column(Integer, default=99991231, nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE | SUPERSEDED | REVOKED
    
    statement = Column(Text, nullable=False)
    structured_payload = Column(JSON, default=dict, nullable=False)
    confidence_score = Column(Float, default=1.0, nullable=False)
    review_status = Column(String(32), default=ReviewStatus.AUTO_EXTRACTED.value, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    version = relationship("DocumentVersion", back_populates="knowledge_items", overlaps="chunks")
    evidence_records = relationship("EvidenceRecord", back_populates="knowledge_item", cascade="all, delete-orphan", overlaps="chunk,evidence_records")

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.version_id"],
            ondelete="CASCADE",
            name="fk_knowledge_tenant_version",
        ),
        UniqueConstraint("tenant_id", "knowledge_id", name="uq_tenant_knowledge_id"),
        Index("idx_knowledge_type_status", "tenant_id", "item_type", "review_status"),
        Index("idx_knowledge_subject_status", "tenant_id", "subject", "status"),
        Index("idx_knowledge_effective_dates", "tenant_id", "effective_from_ymd", "effective_to_ymd"),
    )


class KnowledgeRelation(Base):
    """Bảng lưu trữ quan hệ tri thức giữa 2 Knowledge Items (cùng Tenant)."""
    __tablename__ = "knowledge_relations"

    relation_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    source_knowledge_id = Column(String(64), nullable=False)
    target_knowledge_id = Column(String(64), nullable=False)
    relation_type = Column(String(32), nullable=False)  # SUPERSEDES | MODIFIES | IMPLEMENTS | CONFLICTS_WITH | REFERENCES
    relation_payload = Column(JSON, default=dict, nullable=False)  # target_scope, condition_clause, diff_details
    explanation = Column(Text, default="", nullable=False)
    confidence_score = Column(Float, default=1.0, nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE | INACTIVE
    effective_from_ymd = Column(Integer, default=1, nullable=False)
    effective_to_ymd = Column(Integer, default=99991231, nullable=False)
    detection_method = Column(String(32), default="DETERMINISTIC", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "source_knowledge_id"],
            ["knowledge_items.tenant_id", "knowledge_items.knowledge_id"],
            ondelete="CASCADE",
            name="fk_relation_tenant_source",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_knowledge_id"],
            ["knowledge_items.tenant_id", "knowledge_items.knowledge_id"],
            ondelete="CASCADE",
            name="fk_relation_tenant_target",
        ),
        UniqueConstraint("tenant_id", "source_knowledge_id", "target_knowledge_id", "relation_type", name="uq_tenant_relation_edge"),
        Index("idx_relation_source", "tenant_id", "source_knowledge_id"),
        Index("idx_relation_target", "tenant_id", "target_knowledge_id"),
    )


class EvidenceRecord(Base):
    """Bảng lưu trữ bằng chứng nguyên văn kèm chỉ mục ký tự và SHA256 quote hash."""
    __tablename__ = "evidence_records"

    evidence_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    knowledge_id = Column(String(64), nullable=False)
    chunk_id = Column(String(128), nullable=False)
    source_file = Column(String(255), nullable=True)
    page_number = Column(Integer, nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    section_heading = Column(Text, default="", nullable=False)
    exact_quote_span = Column(Text, nullable=False)
    start_char = Column(Integer, nullable=False)
    end_char = Column(Integer, nullable=False)
    quote_hash = Column(String(64), nullable=False)  # SHA256 của exact_quote_span
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    knowledge_item = relationship("KnowledgeItem", back_populates="evidence_records", overlaps="chunk,evidence_records")
    chunk = relationship("ChunkRecord", back_populates="evidence_records", overlaps="knowledge_item,evidence_records")

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_id"],
            ["knowledge_items.tenant_id", "knowledge_items.knowledge_id"],
            ondelete="CASCADE",
            name="fk_evidence_tenant_knowledge",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["chunk_records.tenant_id", "chunk_records.chunk_id"],
            ondelete="CASCADE",
            name="fk_evidence_tenant_chunk",
        ),
        Index("idx_evidence_knowledge", "tenant_id", "knowledge_id"),
        Index("idx_evidence_chunk", "tenant_id", "chunk_id"),
    )

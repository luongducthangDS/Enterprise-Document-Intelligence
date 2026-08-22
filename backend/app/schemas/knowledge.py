from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class KnowledgeItemDTO(BaseModel):
    knowledge_id: str
    tenant_id: str
    item_type: str
    subject: str
    predicate: str
    object_value: str
    value_numeric: float | None = None
    currency: str = "VND"
    unit: str = ""
    scope: list[str] = Field(default_factory=list)
    role_scope: list[str] = Field(default_factory=list)
    effective_from_ymd: int
    effective_to_ymd: int
    statement: str
    confidence_score: float = 1.0
    review_status: str
    status: str
    created_at: datetime | None = None


class EvidenceRecordDTO(BaseModel):
    evidence_id: str
    knowledge_id: str
    chunk_id: str
    source_file: str | None = None
    section_heading: str = ""
    exact_quote_span: str
    start_char: int
    end_char: int
    quote_hash: str


class KnowledgeItemDetailDTO(BaseModel):
    item: KnowledgeItemDTO
    evidences: list[EvidenceRecordDTO] = Field(default_factory=list)


class EditKnowledgeItemRequest(BaseModel):
    object_value: str | None = None
    value_numeric: float | None = None
    statement: str | None = None
    scope: list[str] | None = None
    role_scope: list[str] | None = None
    effective_from_ymd: int | None = None
    effective_to_ymd: int | None = None
    review_notes: str | None = None


class RejectKnowledgeItemRequest(BaseModel):
    reason: str = Field(min_length=3, description="Lý do từ chối tri thức")


class KnowledgeRelationDTO(BaseModel):
    relation_id: str
    tenant_id: str
    source_knowledge_id: str
    target_knowledge_id: str
    relation_type: str
    explanation: str
    confidence_score: float
    status: str
    effective_from_ymd: int
    created_at: datetime | None = None


class AuditLogDTO(BaseModel):
    log_id: str
    tenant_id: str
    actor_user_id: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

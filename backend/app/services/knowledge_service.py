"""Knowledge Repository & Audit Trail Service for Backend API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.knowledge import (
    AuditLog,
    AuthorityLevel,
    ChunkRecord,
    Document,
    DocumentVersion,
    EvidenceRecord,
    KnowledgeItem,
    KnowledgeRelation,
    KnowledgeType,
    RelationType,
    ReviewStatus,
    Tenant,
)


class KnowledgeRepository:
    def __init__(self, session: Session):
        self.session = session

    # 1. Tenant Operations
    def create_tenant(self, tenant_id: str, slug: str, name: str) -> Tenant:
        stmt = select(Tenant).where((Tenant.tenant_id == tenant_id) | (Tenant.slug == slug))
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing

        tenant = Tenant(tenant_id=tenant_id, slug=slug, name=name)
        self.session.add(tenant)
        self.session.flush()
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        tenant = self.session.get(Tenant, tenant_id)
        if not tenant:
            stmt = select(Tenant).where(Tenant.slug == tenant_id)
            tenant = self.session.execute(stmt).scalar_one_or_none()
        return tenant

    # 2. Document Operations
    def create_document(
        self,
        tenant_id: str,
        document_code: str,
        title: str,
        document_domain: str,
        authority_level: str = AuthorityLevel.COMPANY_POLICY.value,
        access_scope: str = "DEPARTMENT",
        owner_department: str = "GENERAL",
        document_id: str | None = None,
    ) -> Document:
        existing = self.get_document_by_code(tenant_id, document_code)
        if existing:
            return existing

        doc_id = document_id or str(uuid.uuid4())
        doc = Document(
            document_id=doc_id,
            tenant_id=tenant_id,
            document_code=document_code,
            title=title,
            document_domain=document_domain,
            authority_level=authority_level,
            access_scope=access_scope,
            owner_department=owner_department,
            status="ACTIVE",
        )
        self.session.add(doc)
        self.session.flush()
        return doc

    def get_document(self, tenant_id: str, document_id: str) -> Document | None:
        stmt = select(Document).where(Document.tenant_id == tenant_id, Document.document_id == document_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_document_by_code(self, tenant_id: str, document_code: str) -> Document | None:
        stmt = select(Document).where(Document.tenant_id == tenant_id, Document.document_code == document_code)
        return self.session.execute(stmt).scalar_one_or_none()

    # 3. Document Version Operations
    def create_version(
        self,
        tenant_id: str,
        document_id: str,
        version_number: str,
        raw_content: str,
        effective_date_ymd: int = 1,
        expiry_date_ymd: int = 99991231,
        referenced_document_codes: list[str] | None = None,
        version_source: str = "OFFICIAL",
        version_id: str | None = None,
    ) -> DocumentVersion:
        existing = self.get_version_by_number(tenant_id, document_id, version_number)
        if existing:
            return existing

        doc = self.get_document(tenant_id, document_id)
        if not doc:
            raise ValueError(f"Document '{document_id}' không tồn tại hoặc không thuộc tenant '{tenant_id}'")

        ver_id = version_id or str(uuid.uuid4())
        import hashlib

        content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

        ver = DocumentVersion(
            version_id=ver_id,
            document_id=document_id,
            tenant_id=tenant_id,
            version_number=version_number,
            raw_content_hash=content_hash,
            effective_date_ymd=effective_date_ymd,
            expiry_date_ymd=expiry_date_ymd,
            referenced_document_codes=referenced_document_codes or [],
            version_source=version_source,
        )
        self.session.add(ver)
        self.session.flush()
        return ver

    def get_version(self, tenant_id: str, version_id: str) -> DocumentVersion | None:
        stmt = select(DocumentVersion).where(
            DocumentVersion.tenant_id == tenant_id, DocumentVersion.version_id == version_id
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_version_by_number(self, tenant_id: str, document_id: str, version_number: str) -> DocumentVersion | None:
        stmt = select(DocumentVersion).where(
            DocumentVersion.tenant_id == tenant_id,
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    # 4. Chunk Operations
    def create_chunk(
        self,
        tenant_id: str,
        version_id: str,
        chunk_index: int,
        chunk_text: str,
        heading_path: str = "",
        chunk_id: str | None = None,
    ) -> ChunkRecord:
        ver = self.get_version(tenant_id, version_id)
        if not ver:
            raise ValueError(f"Version '{version_id}' không tồn tại hoặc không thuộc tenant '{tenant_id}'")

        cid = chunk_id or f"{tenant_id}:{ver.document_id}:{version_id}:{chunk_index:04d}"
        existing = self.get_chunk(tenant_id, cid)
        if existing:
            return existing

        chunk = ChunkRecord(
            chunk_id=cid,
            version_id=version_id,
            tenant_id=tenant_id,
            chunk_index=chunk_index,
            heading_path=heading_path,
            chunk_text=chunk_text,
            char_count=len(chunk_text),
        )
        self.session.add(chunk)
        self.session.flush()
        return chunk

    def get_chunk(self, tenant_id: str, chunk_id: str) -> ChunkRecord | None:
        stmt = select(ChunkRecord).where(ChunkRecord.tenant_id == tenant_id, ChunkRecord.chunk_id == chunk_id)
        return self.session.execute(stmt).scalar_one_or_none()

    # 5. Knowledge Item Operations
    def create_knowledge_item(
        self,
        tenant_id: str,
        version_id: str,
        item_type: str,
        statement: str,
        structured_payload: dict[str, Any] | None = None,
        confidence_score: float = 1.0,
        subject: str | None = None,
        predicate: str | None = None,
        object_value: str | None = None,
        value_numeric: float | None = None,
        currency: str | None = "VND",
        scope: list[str] | None = None,
        effective_from_ymd: int = 1,
        effective_to_ymd: int = 99991231,
        status: str = "ACTIVE",
        review_status: str = ReviewStatus.AUTO_EXTRACTED.value,
        knowledge_id: str | None = None,
    ) -> KnowledgeItem:
        valid_types = {t.value for t in KnowledgeType}
        if item_type not in valid_types:
            raise ValueError(f"Invalid KnowledgeType '{item_type}'. Must be one of {valid_types}")

        if knowledge_id:
            existing = self.get_knowledge_item(tenant_id, knowledge_id)
            if existing:
                return existing

        kid = knowledge_id or str(uuid.uuid4())
        item = KnowledgeItem(
            knowledge_id=kid,
            tenant_id=tenant_id,
            version_id=version_id,
            item_type=item_type,
            statement=statement.strip(),
            structured_payload=structured_payload or {},
            confidence_score=confidence_score,
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            value_numeric=value_numeric,
            currency=currency,
            scope=scope or ["ALL"],
            effective_from_ymd=effective_from_ymd,
            effective_to_ymd=effective_to_ymd,
            status=status,
            review_status=review_status,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def get_knowledge_item(self, tenant_id: str, knowledge_id: str) -> KnowledgeItem | None:
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.tenant_id == tenant_id, KnowledgeItem.knowledge_id == knowledge_id
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def update_knowledge_item_status(
        self,
        tenant_id: str,
        knowledge_id: str,
        review_status: str,
        status: str | None = None,
    ) -> KnowledgeItem:
        item = self.get_knowledge_item(tenant_id, knowledge_id)
        if not item:
            raise ValueError(f"KnowledgeItem '{knowledge_id}' không tồn tại hoặc không thuộc tenant '{tenant_id}'")
        item.review_status = review_status
        if status:
            item.status = status
        self.session.flush()
        return item

    # 6. Evidence Operations
    def create_evidence(
        self,
        tenant_id: str,
        knowledge_id: str,
        chunk_id: str,
        exact_quote_span: str,
        start_char: int,
        end_char: int,
        section_heading: str = "",
        page_number: int | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
        source_file: str | None = None,
        evidence_id: str | None = None,
    ) -> EvidenceRecord:
        k_item = self.get_knowledge_item(tenant_id, knowledge_id)
        if not k_item:
            raise ValueError(f"KnowledgeItem '{knowledge_id}' không tồn tại hoặc không thuộc tenant '{tenant_id}'")

        chunk = self.get_chunk(tenant_id, chunk_id)
        if not chunk:
            raise ValueError(f"ChunkRecord '{chunk_id}' không tồn tại hoặc không thuộc tenant '{tenant_id}'")

        import hashlib

        quote_hash = hashlib.sha256(exact_quote_span.encode("utf-8")).hexdigest()
        eid = evidence_id or str(uuid.uuid4())

        evidence = EvidenceRecord(
            evidence_id=eid,
            tenant_id=tenant_id,
            knowledge_id=knowledge_id,
            chunk_id=chunk_id,
            source_file=source_file,
            page_number=page_number,
            page_start=page_start,
            page_end=page_end,
            section_heading=section_heading,
            exact_quote_span=exact_quote_span,
            start_char=start_char,
            end_char=end_char,
            quote_hash=quote_hash,
        )
        self.session.add(evidence)
        self.session.flush()
        return evidence

    # 7. Knowledge Relation Operations
    def create_relation(
        self,
        tenant_id: str,
        source_knowledge_id: str,
        target_knowledge_id: str,
        relation_type: str,
        relation_payload: dict[str, Any] | None = None,
        explanation: str = "",
        confidence_score: float = 1.0,
        status: str = "ACTIVE",
        effective_from_ymd: int = 1,
        effective_to_ymd: int = 99991231,
        detection_method: str = "DETERMINISTIC",
        relation_id: str | None = None,
    ) -> KnowledgeRelation:
        valid_relations = {r.value for r in RelationType}
        if relation_type not in valid_relations:
            raise ValueError(f"Invalid RelationType '{relation_type}'. Must be one of {valid_relations}")

        stmt = select(KnowledgeRelation).where(
            KnowledgeRelation.tenant_id == tenant_id,
            KnowledgeRelation.source_knowledge_id == source_knowledge_id,
            KnowledgeRelation.target_knowledge_id == target_knowledge_id,
            KnowledgeRelation.relation_type == relation_type,
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing

        rel_id = relation_id or str(uuid.uuid4())
        relation = KnowledgeRelation(
            relation_id=rel_id,
            tenant_id=tenant_id,
            source_knowledge_id=source_knowledge_id,
            target_knowledge_id=target_knowledge_id,
            relation_type=relation_type,
            relation_payload=relation_payload or {},
            explanation=explanation,
            confidence_score=confidence_score,
            status=status,
            effective_from_ymd=effective_from_ymd,
            effective_to_ymd=effective_to_ymd,
            detection_method=detection_method,
        )
        self.session.add(relation)
        self.session.flush()
        return relation

    def get_relation(self, tenant_id: str, relation_id: str) -> KnowledgeRelation | None:
        stmt = select(KnowledgeRelation).where(
            KnowledgeRelation.tenant_id == tenant_id, KnowledgeRelation.relation_id == relation_id
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_relation_by_id(self, tenant_id: str, relation_id: str) -> KnowledgeRelation | None:
        return self.get_relation(tenant_id, relation_id)

    def get_evidences_by_knowledge_id(self, tenant_id: str, knowledge_id: str) -> list[EvidenceRecord]:
        stmt = select(EvidenceRecord).where(
            EvidenceRecord.tenant_id == tenant_id, EvidenceRecord.knowledge_id == knowledge_id
        )
        return list(self.session.scalars(stmt).all())

    def get_incoming_relations(
        self,
        tenant_id: str,
        target_knowledge_id: str,
        relation_type: str | None = None,
        active_only: bool = True,
    ) -> list[KnowledgeRelation]:
        stmt = select(KnowledgeRelation).where(
            KnowledgeRelation.tenant_id == tenant_id,
            KnowledgeRelation.target_knowledge_id == target_knowledge_id,
        )
        if relation_type:
            stmt = stmt.where(KnowledgeRelation.relation_type == relation_type)
        if active_only:
            stmt = stmt.where(KnowledgeRelation.status == "ACTIVE")
        return list(self.session.scalars(stmt).all())

    def get_knowledge_items_by_subject(
        self,
        tenant_id: str,
        subject: str,
        target_date_ymd: int | None = None,
        approved_only: bool = True,
    ) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.tenant_id == tenant_id,
            KnowledgeItem.subject == subject,
            KnowledgeItem.status == "ACTIVE",
        )
        if approved_only:
            stmt = stmt.where(
                KnowledgeItem.review_status.in_(["APPROVED", "ACTIVE", ReviewStatus.AUTO_EXTRACTED.value])
            )
        if target_date_ymd is not None:
            stmt = stmt.where(
                KnowledgeItem.effective_from_ymd <= target_date_ymd,
                KnowledgeItem.effective_to_ymd >= target_date_ymd,
            )
        return list(self.session.scalars(stmt).all())

    def trace_knowledge_lineage(self, tenant_id: str, knowledge_id: str) -> dict[str, Any]:
        k_item = self.get_knowledge_item(tenant_id, knowledge_id)
        if not k_item:
            raise ValueError(f"KnowledgeItem '{knowledge_id}' không tồn tại")

        ver = self.get_version(tenant_id, k_item.version_id)
        doc = self.get_document(tenant_id, ver.document_id) if ver else None

        evidences = self.get_evidences_by_knowledge_id(tenant_id, knowledge_id)
        evidence_lineage = []
        for evi in evidences:
            chunk = self.get_chunk(tenant_id, evi.chunk_id)
            evidence_lineage.append(
                {
                    "evidence_id": evi.evidence_id,
                    "exact_quote_span": evi.exact_quote_span,
                    "start_char": evi.start_char,
                    "end_char": evi.end_char,
                    "quote_hash": evi.quote_hash,
                    "section_heading": evi.section_heading,
                    "chunk": {
                        "chunk_id": chunk.chunk_id if chunk else None,
                        "chunk_index": chunk.chunk_index if chunk else None,
                        "heading_path": chunk.heading_path if chunk else None,
                    }
                    if chunk
                    else None,
                }
            )

        return {
            "knowledge": {
                "knowledge_id": k_item.knowledge_id,
                "tenant_id": k_item.tenant_id,
                "item_type": k_item.item_type,
                "statement": k_item.statement,
                "structured_payload": k_item.structured_payload,
                "confidence_score": k_item.confidence_score,
                "review_status": k_item.review_status,
            },
            "document_version": {
                "version_id": ver.version_id if ver else None,
                "version_number": ver.version_number if ver else None,
                "raw_content_hash": ver.raw_content_hash if ver else None,
                "effective_date_ymd": ver.effective_date_ymd if ver else None,
            }
            if ver
            else None,
            "document": {
                "document_id": doc.document_id if doc else None,
                "document_code": doc.document_code if doc else None,
                "title": doc.title if doc else None,
                "document_domain": doc.document_domain if doc else None,
                "authority_level": doc.authority_level if doc else None,
                "owner_department": doc.owner_department if doc else None,
            }
            if doc
            else None,
            "evidences": evidence_lineage,
        }


def log_audit(
    session: Session,
    tenant_id: str,
    actor_user_id: str,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        log_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        created_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    session.flush()
    return entry


def get_audit_trail(
    session: Session,
    tenant_id: str,
    entity_id: str | None = None,
    action: str | None = None,
    limit: int = 50,
) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())

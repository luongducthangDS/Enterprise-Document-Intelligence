from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.dependencies.auth_deps import get_current_user, require_role
from app.core.config import get_settings
from app.core.knowledge_db import get_knowledge_session as get_session
from app.domain.models.knowledge import (
    KnowledgeItem,
    KnowledgeRelation,
    ReviewStatus,
)
from app.schemas.common import wrap_response
from app.schemas.knowledge import (
    AuditLogDTO,
    EditKnowledgeItemRequest,
    EvidenceRecordDTO,
    KnowledgeItemDetailDTO,
    KnowledgeItemDTO,
    KnowledgeRelationDTO,
    RejectKnowledgeItemRequest,
)
from app.services.knowledge_service import (
    KnowledgeRepository,
    get_audit_trail,
    log_audit,
)

router = APIRouter()


def _resolve_tenant_id(requested_tenant_id: str | None) -> str:
    """Bind Knowledge API access to the backend's trusted active tenant."""
    active_tenant = get_settings().active_tenant.strip().lower()
    if requested_tenant_id and requested_tenant_id.strip().lower() != active_tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    return active_tenant


@router.get("/items")
async def list_knowledge_items(
    request: Request,
    tenant_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Danh sách các tri thức có cấu trúc kèm bộ lọc review_status và subject."""
    tenant_id = _resolve_tenant_id(tenant_id)
    with get_session() as session:
        stmt = select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant_id)
        if review_status:
            stmt = stmt.where(KnowledgeItem.review_status == review_status)
        if subject:
            stmt = stmt.where(KnowledgeItem.subject == subject)
        stmt = stmt.order_by(KnowledgeItem.created_at.desc()).offset(offset).limit(limit)

        items = session.scalars(stmt).all()
        dto_list = [
            KnowledgeItemDTO(
                knowledge_id=it.knowledge_id,
                tenant_id=it.tenant_id,
                item_type=it.item_type,
                subject=it.subject or "",
                predicate=it.predicate or "",
                object_value=it.object_value or "",
                value_numeric=it.value_numeric,
                currency=it.currency or "VND",
                unit=str(it.structured_payload.get("unit", "")) if it.structured_payload else "",
                scope=it.scope or [],
                role_scope=it.structured_payload.get("role_scope", []) if it.structured_payload else [],
                effective_from_ymd=it.effective_from_ymd,
                effective_to_ymd=it.effective_to_ymd,
                statement=it.statement,
                confidence_score=it.confidence_score,
                review_status=it.review_status,
                status=it.status,
                created_at=it.created_at,
            ).model_dump()
            for it in items
        ]
        return wrap_response(
            dto_list,
            request,
            pagination={"limit": limit, "offset": offset, "total": len(dto_list)},
        )


@router.get("/items/{item_id}")
async def get_knowledge_item_detail(
    item_id: str,
    request: Request,
    tenant_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Chi tiết một tri thức có cấu trúc kèm đầy đủ bằng chứng đối chiếu."""
    tenant_id = _resolve_tenant_id(tenant_id)
    with get_session() as session:
        repo = KnowledgeRepository(session)
        item = repo.get_knowledge_item(tenant_id, item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found")

        evidences = repo.get_evidences_by_knowledge_id(tenant_id, item_id)

        detail = KnowledgeItemDetailDTO(
            item=KnowledgeItemDTO(
                knowledge_id=item.knowledge_id,
                tenant_id=item.tenant_id,
                item_type=item.item_type,
                subject=item.subject or "",
                predicate=item.predicate or "",
                object_value=item.object_value or "",
                value_numeric=item.value_numeric,
                currency=item.currency or "VND",
                unit=str(item.structured_payload.get("unit", "")) if item.structured_payload else "",
                scope=item.scope or [],
                role_scope=item.structured_payload.get("role_scope", []) if item.structured_payload else [],
                effective_from_ymd=item.effective_from_ymd,
                effective_to_ymd=item.effective_to_ymd,
                statement=item.statement,
                confidence_score=item.confidence_score,
                review_status=item.review_status,
                status=item.status,
                created_at=item.created_at,
            ),
            evidences=[
                EvidenceRecordDTO(
                    evidence_id=ev.evidence_id,
                    knowledge_id=ev.knowledge_id,
                    chunk_id=ev.chunk_id,
                    source_file=ev.source_file,
                    section_heading=ev.section_heading,
                    exact_quote_span=ev.exact_quote_span,
                    start_char=ev.start_char,
                    end_char=ev.end_char,
                    quote_hash=ev.quote_hash,
                )
                for ev in evidences
            ],
        )
        return wrap_response(detail.model_dump(), request)


@router.patch("/items/{item_id}/approve")
async def approve_knowledge_item(
    item_id: str,
    request: Request,
    tenant_id: str | None = Query(default=None),
    current_user: dict = Depends(require_role(["ADMIN", "SUPER_ADMIN", "HR_ADMIN", "HR_OPERATOR"])),
) -> dict[str, Any]:
    """Phê duyệt tri thức (HITL Review -> APPROVED / ACTIVE)."""
    tenant_id = _resolve_tenant_id(tenant_id)
    user_id = current_user.get("user_id", "admin")
    role = current_user.get("role", "ADMIN")

    with get_session() as session:
        repo = KnowledgeRepository(session)
        item = repo.get_knowledge_item(tenant_id, item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found")

        old_status = item.review_status
        item.review_status = ReviewStatus.APPROVED.value
        item.status = "ACTIVE"
        session.flush()

        log_audit(
            session=session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            actor_role=role,
            action="HITL_APPROVED",
            entity_type="knowledge_item",
            entity_id=item_id,
            payload={"old_status": old_status, "new_status": item.review_status},
        )
        return wrap_response({"knowledge_id": item_id, "review_status": item.review_status}, request)


@router.patch("/items/{item_id}/reject")
async def reject_knowledge_item(
    item_id: str,
    payload: RejectKnowledgeItemRequest,
    request: Request,
    tenant_id: str | None = Query(default=None),
    current_user: dict = Depends(require_role(["ADMIN", "SUPER_ADMIN", "HR_ADMIN", "HR_OPERATOR"])),
) -> dict[str, Any]:
    """Từ chối tri thức kèm lý do."""
    tenant_id = _resolve_tenant_id(tenant_id)
    user_id = current_user.get("user_id", "admin")
    role = current_user.get("role", "ADMIN")

    with get_session() as session:
        repo = KnowledgeRepository(session)
        item = repo.get_knowledge_item(tenant_id, item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found")

        item.review_status = ReviewStatus.REJECTED.value
        item.status = "INACTIVE"
        session.flush()

        log_audit(
            session=session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            actor_role=role,
            action="HITL_REJECTED",
            entity_type="knowledge_item",
            entity_id=item_id,
            payload={"reason": payload.reason},
        )
        return wrap_response({"knowledge_id": item_id, "review_status": item.review_status}, request)


@router.patch("/items/{item_id}/edit")
async def edit_knowledge_item(
    item_id: str,
    payload: EditKnowledgeItemRequest,
    request: Request,
    tenant_id: str | None = Query(default=None),
    current_user: dict = Depends(require_role(["ADMIN", "SUPER_ADMIN", "HR_ADMIN", "HR_OPERATOR"])),
) -> dict[str, Any]:
    """Chỉnh sửa thông số tri thức trước khi duyệt."""
    tenant_id = _resolve_tenant_id(tenant_id)
    user_id = current_user.get("user_id", "admin")
    role = current_user.get("role", "ADMIN")

    with get_session() as session:
        repo = KnowledgeRepository(session)
        item = repo.get_knowledge_item(tenant_id, item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found")

        changes: dict[str, Any] = {}
        if payload.object_value is not None:
            changes["object_value"] = {"old": item.object_value, "new": payload.object_value}
            item.object_value = payload.object_value
        if payload.value_numeric is not None:
            changes["value_numeric"] = {"old": item.value_numeric, "new": payload.value_numeric}
            item.value_numeric = payload.value_numeric
        if payload.statement is not None:
            changes["statement"] = {"old": item.statement, "new": payload.statement}
            item.statement = payload.statement
        if payload.scope is not None:
            item.scope = payload.scope
        if payload.role_scope is not None:
            changes["role_scope"] = {
                "old": list((item.structured_payload or {}).get("role_scope", [])),
                "new": payload.role_scope,
            }
            structured_payload = dict(item.structured_payload or {})
            structured_payload["role_scope"] = payload.role_scope
            item.structured_payload = structured_payload
        if payload.effective_from_ymd is not None:
            item.effective_from_ymd = payload.effective_from_ymd
        if payload.effective_to_ymd is not None:
            item.effective_to_ymd = payload.effective_to_ymd

        item.review_status = ReviewStatus.APPROVED.value
        item.status = "ACTIVE"
        session.flush()

        log_audit(
            session=session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            actor_role=role,
            action="HITL_EDITED",
            entity_type="knowledge_item",
            entity_id=item_id,
            payload={"changes": changes, "notes": payload.review_notes},
        )
        return wrap_response({"knowledge_id": item_id, "review_status": item.review_status}, request)


@router.get("/relations")
async def list_knowledge_relations(
    request: Request,
    tenant_id: str | None = Query(default=None),
    relation_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Danh sách các quan hệ tri thức (SUPERSEDES, MODIFIES, CONFLICTS_WITH, etc.)."""
    tenant_id = _resolve_tenant_id(tenant_id)
    with get_session() as session:
        stmt = select(KnowledgeRelation).where(KnowledgeRelation.tenant_id == tenant_id)
        if relation_type:
            stmt = stmt.where(KnowledgeRelation.relation_type == relation_type)
        stmt = stmt.order_by(KnowledgeRelation.created_at.desc()).limit(limit)

        relations = session.scalars(stmt).all()
        dto_list = [
            KnowledgeRelationDTO(
                relation_id=rel.relation_id,
                tenant_id=rel.tenant_id,
                source_knowledge_id=rel.source_knowledge_id,
                target_knowledge_id=rel.target_knowledge_id,
                relation_type=rel.relation_type,
                explanation=rel.explanation,
                confidence_score=rel.confidence_score,
                status=rel.status,
                effective_from_ymd=rel.effective_from_ymd,
                created_at=rel.created_at,
            ).model_dump()
            for rel in relations
        ]
        return wrap_response(dto_list, request)


@router.patch("/relations/{relation_id}/approve")
async def approve_knowledge_relation(
    relation_id: str,
    request: Request,
    tenant_id: str | None = Query(default=None),
    current_user: dict = Depends(require_role(["ADMIN", "SUPER_ADMIN", "HR_ADMIN", "HR_OPERATOR"])),
) -> dict[str, Any]:
    """Xác nhận quan hệ tri thức."""
    tenant_id = _resolve_tenant_id(tenant_id)
    user_id = current_user.get("user_id", "admin")
    role = current_user.get("role", "ADMIN")

    with get_session() as session:
        repo = KnowledgeRepository(session)
        rel = repo.get_relation_by_id(tenant_id, relation_id)
        if not rel:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relation not found")

        rel.status = "ACTIVE"
        session.flush()

        log_audit(
            session=session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            actor_role=role,
            action="HITL_APPROVED",
            entity_type="knowledge_relation",
            entity_id=relation_id,
            payload={"relation_type": rel.relation_type},
        )
        return wrap_response({"relation_id": relation_id, "status": rel.status}, request)


@router.get("/audit")
async def list_audit_trail(
    request: Request,
    tenant_id: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(require_role(["ADMIN", "SUPER_ADMIN", "HR_ADMIN", "HR_OPERATOR"])),
) -> dict[str, Any]:
    """Truy vấn nhật ký kiểm toán (Audit Trail) phục vụ governance và tuân thủ."""
    tenant_id = _resolve_tenant_id(tenant_id)
    with get_session() as session:
        logs = get_audit_trail(session, tenant_id=tenant_id, entity_id=entity_id, action=action, limit=limit)
        dto_list = [
            AuditLogDTO(
                log_id=lg.log_id,
                tenant_id=lg.tenant_id,
                actor_user_id=lg.actor_user_id,
                actor_role=lg.actor_role,
                action=lg.action,
                entity_type=lg.entity_type,
                entity_id=lg.entity_id,
                payload=lg.payload or {},
                created_at=lg.created_at,
            ).model_dump()
            for lg in logs
        ]
        return wrap_response(dto_list, request)

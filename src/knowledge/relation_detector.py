"""Relation Detection Pipeline for Knowledge Layer.

Phát hiện tự động và suy luận quan hệ tri thức giữa các Knowledge Items:
1. SUPERSEDES: Item mới thay thế Item cũ (cùng subject, predicate; ngày áp dụng mới hơn).
2. MODIFIES: Quyết định điều chỉnh bổ sung cho Quy chế/Quy định gốc.
3. CONFLICTS_WITH: Hai quy định cùng hiệu lực, cùng phạm vi nhưng xung đột giá trị.
4. REFERENCES: Quy định dẫn chiếu văn bản liên quan.
"""
from __future__ import annotations

import logging
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.knowledge.audit import log_audit
from src.knowledge.models import (
    KnowledgeItem,
    KnowledgeRelation,
    RelationType,
    ReviewStatus,
)
from src.knowledge.repository import KnowledgeRepository

logger = logging.getLogger(__name__)


def _scopes_overlap(scope_a: list[str], scope_b: list[str]) -> bool:
    """Kiểm tra hai danh sách phạm vi có giao nhau không (hoặc có ALL)."""
    if "ALL" in scope_a or "ALL" in scope_b:
        return True
    return bool(set(scope_a) & set(scope_b))


def _roles_overlap(role_a: list[str], role_b: list[str]) -> bool:
    """Kiểm tra hai danh sách role có giao nhau không (hoặc có ALL/STAFF)."""
    if "ALL" in role_a or "ALL" in role_b:
        return True
    return bool(set(role_a) & set(role_b))


def detect_knowledge_relations(
    session: Session,
    tenant_id: str,
    actor_user_id: str = "system_relation_detector",
    actor_role: str = "SYSTEM",
) -> list[dict[str, Any]]:
    """Quét toàn bộ KnowledgeItems trong Tenant và sinh quan hệ tri thức tự động."""
    repo = KnowledgeRepository(session)
    
    # Lấy tất cả items hợp lệ của tenant
    stmt = (
        select(KnowledgeItem)
        .where(
            KnowledgeItem.tenant_id == tenant_id,
            KnowledgeItem.status == "ACTIVE",
        )
        .order_by(KnowledgeItem.effective_from_ymd.asc())
    )
    items = list(session.scalars(stmt).all())
    detected_relations: list[dict[str, Any]] = []

    n = len(items)
    for i in range(n):
        for j in range(i + 1, n):
            item_a = items[i]  # older or equal effective date
            item_b = items[j]  # newer or equal effective date

            # Đảm bảo cùng subject
            if item_a.subject != item_b.subject:
                continue

            # Kiểm tra cùng predicate
            same_predicate = (item_a.predicate == item_b.predicate)
            overlap_scope = _scopes_overlap(item_a.scope or ["ALL"], item_b.scope or ["ALL"])
            role_a = (item_a.structured_payload.get("role_scope") if item_a.structured_payload else None) or ["STAFF"]
            role_b = (item_b.structured_payload.get("role_scope") if item_b.structured_payload else None) or ["STAFF"]
            overlap_role = _roles_overlap(role_a, role_b)

            if not (same_predicate and overlap_scope and overlap_role):
                continue

            # 1. Phát hiện SUPERSEDES / MODIFIES
            # item_b có ngày hiệu lực mới hơn item_a
            if item_b.effective_from_ymd > item_a.effective_from_ymd:
                # Kiểm tra nếu item_b là DECISION hoặc có modifier flag
                rel_type = RelationType.SUPERSEDES.value
                if item_b.item_type == "DECISION" or item_b.structured_payload.get("modifies_doc"):
                    rel_type = RelationType.MODIFIES.value

                explanation = (
                    f"Tri thức {item_b.knowledge_id} ({item_b.subject}:{item_b.predicate}) có hiệu lực từ {item_b.effective_from_ymd} "
                    f"{rel_type} tri thức cũ {item_a.knowledge_id} (hiệu lực từ {item_a.effective_from_ymd})."
                )

                try:
                    rel = repo.create_relation(
                        tenant_id=tenant_id,
                        source_knowledge_id=item_b.knowledge_id,
                        target_knowledge_id=item_a.knowledge_id,
                        relation_type=rel_type,
                        explanation=explanation,
                        relation_payload={
                            "source_value": item_b.object_value,
                            "target_value": item_a.object_value,
                            "source_effective": item_b.effective_from_ymd,
                            "target_effective": item_a.effective_from_ymd,
                            "scope": list(set(item_b.scope or []) | set(item_a.scope or [])),
                        },
                        confidence_score=0.95,
                    )
                    log_audit(
                        session=session,
                        tenant_id=tenant_id,
                        actor_user_id=actor_user_id,
                        actor_role=actor_role,
                        action="RELATION_DETECTED",
                        entity_type="knowledge_relation",
                        entity_id=rel.relation_id,
                        payload={
                            "relation_type": rel_type,
                            "source_id": item_b.knowledge_id,
                            "target_id": item_a.knowledge_id,
                        },
                    )
                    detected_relations.append({
                        "relation_id": rel.relation_id,
                        "relation_type": rel_type,
                        "source_id": item_b.knowledge_id,
                        "target_id": item_a.knowledge_id,
                        "explanation": explanation,
                    })
                except Exception as e:
                    logger.debug("Relation already exists or failed: %s", e)

            # 2. Phát hiện CONFLICTS_WITH
            # Cùng ngày hoặc khoảng thời gian chồng lấn, nhưng giá trị khác nhau
            elif (
                item_a.effective_from_ymd == item_b.effective_from_ymd
                and item_a.object_value != item_b.object_value
            ):
                explanation = (
                    f"Xung đột giá trị giữa {item_a.knowledge_id} ('{item_a.object_value}') "
                    f"và {item_b.knowledge_id} ('{item_b.object_value}') trong cùng khoảng thời gian hiệu lực."
                )
                try:
                    rel = repo.create_relation(
                        tenant_id=tenant_id,
                        source_knowledge_id=item_b.knowledge_id,
                        target_knowledge_id=item_a.knowledge_id,
                        relation_type=RelationType.CONFLICTS_WITH.value,
                        explanation=explanation,
                        relation_payload={
                            "conflict_values": [item_a.object_value, item_b.object_value],
                        },
                        confidence_score=0.90,
                    )
                    log_audit(
                        session=session,
                        tenant_id=tenant_id,
                        actor_user_id=actor_user_id,
                        actor_role=actor_role,
                        action="RELATION_DETECTED",
                        entity_type="knowledge_relation",
                        entity_id=rel.relation_id,
                        payload={"relation_type": "CONFLICTS_WITH"},
                    )
                    detected_relations.append({
                        "relation_id": rel.relation_id,
                        "relation_type": RelationType.CONFLICTS_WITH.value,
                        "source_id": item_b.knowledge_id,
                        "target_id": item_a.knowledge_id,
                        "explanation": explanation,
                    })
                except Exception as e:
                    logger.debug("Conflict relation failed: %s", e)

    return detected_relations

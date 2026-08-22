"""Audit Log and Governance Trail for Knowledge Layer.

Lưu vết toàn bộ thao tác trích xuất, phát hiện quan hệ, phê duyệt HITL và truy vấn.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.knowledge.models import AuditLog


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
    """Ghi một bản ghi nhật ký kiểm toán (Audit Log) cho Knowledge Layer."""
    log_entry = AuditLog(
        log_id=f"audit_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        created_at=datetime.now(timezone.utc),
    )
    session.add(log_entry)
    session.flush()
    return log_entry


def get_audit_trail(
    session: Session,
    tenant_id: str,
    entity_id: str | None = None,
    entity_type: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[AuditLog]:
    """Truy vấn danh sách audit trail theo điều kiện lọc."""
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())

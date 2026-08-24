import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import require_role
from app.api.dependencies.db_deps import get_db
from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundError
from app.domain.models.audit import AuditLogDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.schemas.admin import UserAccessUpdate
from app.schemas.common import wrap_response

router = APIRouter()

ROLE_CAPABILITIES = {
    "EMPLOYEE": ["chat.use", "ticket.own", "knowledge.company", "knowledge.department"],
    "DEPARTMENT_MANAGER": ["chat.use", "ticket.manage.department", "document.manage.department"],
    "SUPER_ADMIN": ["*"],
}


@router.get("/access-model")
async def get_access_model(request: Request, current_user: dict[str, Any] = Depends(require_role(["SUPER_ADMIN"]))) -> dict[str, Any]:
    return wrap_response({"roles": ROLE_CAPABILITIES, "scopes": ["COMPANY_WIDE", "DEPARTMENT", "ROLE", "RESTRICTED"]}, request)


@router.get("/users")
async def list_users(request: Request, current_user: dict[str, Any] = Depends(require_role(["SUPER_ADMIN"])), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    rows = (await db.execute(select(UserDB, ProfileDB).join(ProfileDB, ProfileDB.id == UserDB.id).order_by(ProfileDB.display_name))).all()
    data = [{"user_id": str(user.id), "email": user.email, "display_name": profile.display_name, "role": profile.role.upper(), "department": profile.department or ""} for user, profile in rows]
    return wrap_response(data, request)


@router.patch("/users/{user_id}/access")
async def update_user_access(user_id: str, payload: UserAccessUpdate, request: Request, current_user: dict[str, Any] = Depends(require_role(["SUPER_ADMIN"])), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        target_id = uuid.UUID(user_id)
    except ValueError as exc:
        raise NotFoundError(code="USER_NOT_FOUND", message="Không tìm thấy người dùng.") from exc
    role = payload.role.upper().strip()
    if role not in ROLE_CAPABILITIES:
        raise AppException(status_code=422, code="INVALID_ROLE", message="Vai trò không hợp lệ.")
    profile = await db.get(ProfileDB, target_id)
    if profile is None:
        raise NotFoundError(code="USER_NOT_FOUND", message="Không tìm thấy người dùng.")
    before = {"role": profile.role.upper(), "department": profile.department or ""}
    if before["role"] == "SUPER_ADMIN" and role != "SUPER_ADMIN":
        super_admin_count = await db.scalar(
            select(func.count()).select_from(ProfileDB).where(func.upper(ProfileDB.role) == "SUPER_ADMIN")
        )
        if int(super_admin_count or 0) <= 1:
            raise AppException(
                status_code=409,
                code="LAST_SUPER_ADMIN_REQUIRED",
                message="Hệ thống phải còn ít nhất một Quản trị hệ thống.",
            )

    profile.role = role
    profile.department = payload.department.strip()
    after = {"role": profile.role, "department": profile.department}
    db.add(AuditLogDB(tenant=get_settings().active_tenant, actor_id=uuid.UUID(current_user["user_id"]), action="USER_ACCESS_UPDATED", resource_type="profile", resource_id=str(profile.id), before_state=before, after_state=after))
    await db.commit()
    return wrap_response({"user_id": str(profile.id), **after}, request)


@router.get("/audit-logs")
async def list_audit_logs(request: Request, limit: int = 100, current_user: dict[str, Any] = Depends(require_role(["SUPER_ADMIN"])), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    safe_limit = min(max(limit, 1), 200)
    logs = (await db.execute(select(AuditLogDB).where(AuditLogDB.tenant == get_settings().active_tenant).order_by(desc(AuditLogDB.created_at)).limit(safe_limit))).scalars().all()
    data = [{"audit_id": str(log.id), "actor_id": str(log.actor_id), "action": log.action, "resource_type": log.resource_type, "resource_id": log.resource_id, "before": log.before_state, "after": log.after_state, "created_at": log.created_at.isoformat()} for log in logs]
    return wrap_response(data, request)
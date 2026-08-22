"""Trusted Tenant & Collection Resolver Module.

Chịu trách nhiệm phân giải và cô lập không gian tên (namespace) collection Chroma
từ định danh tenant đã được xác thực (Authenticated UserContext).

NGUYÊN TẮC BẢO MẬT:
1. Tuyệt đối không nhận collection_name hoặc tenant_id từ request body / query param không xác thực.
2. Tenant ID phải tuân thủ định dạng chuẩn an toàn (^[a-zA-Z0-9_-]{1,64}$).
3. Đảm bảo 100% không thể rò rỉ hoặc truy vấn chéo giữa các tenant.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.config import get_settings

if TYPE_CHECKING:
    from src.security.models import UserContext

_TENANT_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_tenant_id(tenant_id: str) -> str:
    """Xác thực và chuẩn hóa tenant_id."""
    clean = str(tenant_id or "").strip().lower()
    if not clean or not _TENANT_ID_REGEX.match(clean):
        raise ValueError(
            f"Invalid tenant_id '{tenant_id}'. Must be 1-64 alphanumeric, hyphen, or underscore characters."
        )
    return clean


def get_tenant_collection_name(tenant_id: str) -> str:
    """Sinh tên collection Chroma cô lập theo chuẩn: tenant_{tenant_id}_knowledge."""
    clean_tenant = validate_tenant_id(tenant_id)
    return f"tenant_{clean_tenant}_knowledge"


def resolve_tenant_collection(user_context: UserContext | None = None, allow_dev_fallback: bool = False) -> str:
    """Xác định collection name tin cậy từ UserContext đã xác thực.

    Fail-closed: Trong production, BẮT BUỘC phải có tenant_id từ UserContext hợp lệ.
    Tuyệt đối không tự động fallback sang default tenant.
    """
    settings = get_settings()
    if user_context and user_context.tenant_id:
        clean_tenant = validate_tenant_id(user_context.tenant_id)
        return get_tenant_collection_name(clean_tenant)

    if settings.app_env == "production" and not allow_dev_fallback:
        raise PermissionError(
            "CRITICAL SECURITY GUARD: Missing authenticated tenant_id in production request context. Access Denied."
        )

    clean_tenant = validate_tenant_id(settings.active_tenant)
    return get_tenant_collection_name(clean_tenant)


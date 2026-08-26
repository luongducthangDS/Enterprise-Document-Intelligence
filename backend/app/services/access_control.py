"""Central role and document-scope authorization rules."""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.documents import DocumentDB

EMPLOYEE = "EMPLOYEE"
DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
SUPER_ADMIN = "SUPER_ADMIN"
ASSIGNABLE_ROLES = frozenset({EMPLOYEE, DEPARTMENT_MANAGER, SUPER_ADMIN})


def canonical_department(value: str | None) -> str:
    raw = str(value or "").strip()
    ascii_value = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Z0-9]+", "_", ascii_value.upper()).strip("_")
    aliases = {
        "HUMAN_RESOURCES": "HR",
        "HUMAN_RESOURCE": "HR",
        "NHAN_SU": "HR",
        "KE_TOAN": "ACCOUNTING",
        "ACCOUNTANCY": "ACCOUNTING",
        "PRODUCT_MANAGEMENT": "PRODUCT",
        "SAN_PHAM": "PRODUCT",
    }
    return aliases.get(normalized, normalized) or "GENERAL"


def normalized_role(user: dict[str, Any]) -> str:
    return str(user.get("role") or "").upper().strip()

def department_targets(department: str | None) -> set[str]:
    canonical = canonical_department(department)
    if canonical == "HR":
        return {"HR", "CB", "ER", "TA", "LD", "HRBP"}
    return {canonical}



def same_department(user: dict[str, Any], department: str | None) -> bool:
    return canonical_department(user.get("department")) == canonical_department(department)


def can_read_document(user: dict[str, Any], document: "DocumentDB") -> bool:
    role = normalized_role(user)
    if role == SUPER_ADMIN:
        return True
    confidentiality = str(document.confidentiality or "").upper().strip()
    if confidentiality in {"RESTRICTED", "CONFIDENTIAL"}:
        return False
    scope = str(document.access_scope or "").upper().strip()
    if scope == "COMPANY_WIDE":
        return True
    if scope == "DEPARTMENT":
        return same_department(user, document.department)
    if scope == "ROLE":
        return same_department(user, document.department) and role == str(document.authorized_role or "").upper().strip()
    if scope == "RESTRICTED":
        try:
            return document.owner_user_id == uuid.UUID(str(user.get("user_id")))
        except (TypeError, ValueError):
            return False
    return False


def can_manage_document(user: dict[str, Any], document: "DocumentDB") -> bool:
    role = normalized_role(user)
    return role == SUPER_ADMIN or (role == DEPARTMENT_MANAGER and same_department(user, document.department))

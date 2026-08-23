"""Enterprise Security and Access Control Module."""

from src.security.authorization import (
    AuthorizationEngine,
    get_authorization_engine,
    runtime_upload_access_condition,
    runtime_upload_access_filters,
    runtime_upload_metadata_allowed,
)
from src.security.departments import canonical_department
from src.security.models import (
    AccessScope,
    DocumentDomain,
    SensitivityLevel,
    UserContext,
    UserRole,
)

__all__ = [
    "AccessScope",
    "AuthorizationEngine",
    "DocumentDomain",
    "SensitivityLevel",
    "UserContext",
    "UserRole",
    "canonical_department",
    "get_authorization_engine",
    "runtime_upload_access_condition",
    "runtime_upload_access_filters",
    "runtime_upload_metadata_allowed",
]

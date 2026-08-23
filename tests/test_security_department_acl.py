from src.agents.nodes.retrieval import _metadata_lifecycle_allowed, _predicate_leaf_count, _retrieval_filters
from src.config import Settings
from src.security import (
    AccessScope,
    AuthorizationEngine,
    DocumentDomain,
    UserContext,
    UserRole,
    canonical_department,
    runtime_upload_metadata_allowed,
)
from src.security.models import DocumentSecurityProfile


def _user(department: str, role: UserRole = UserRole.DEPARTMENT_USER) -> UserContext:
    return UserContext(tenant_id="nexatech", user_id="user-1", department=department, role=role)


def _document(department: str, scope: AccessScope = AccessScope.DEPARTMENT) -> DocumentSecurityProfile:
    return DocumentSecurityProfile(
        source_file="policy.md",
        domain=DocumentDomain.COMPANY_POLICY,
        department=department,
        access_scope=scope,
        authorized_departments=[canonical_department(department)],
    )


def test_department_aliases_are_canonical() -> None:
    assert canonical_department("Product") == "PRODUCT"
    assert canonical_department("Kế toán") == "ACCOUNTING"
    assert canonical_department("Human Resources") == "HR"


def test_company_wide_legacy_document_cannot_cross_department() -> None:
    engine = AuthorizationEngine()
    document = _document("HR", AccessScope.COMPANY_WIDE)
    assert engine.evaluate_access(_user("HR"), document) is True
    assert engine.evaluate_access(_user("PRODUCT"), document) is False


def test_admin_cannot_cross_department() -> None:
    engine = AuthorizationEngine()
    assert engine.evaluate_access(_user("HR", UserRole.ADMIN), _document("PRODUCT")) is False


def test_runtime_company_wide_upload_is_department_bound() -> None:
    metadata = {
        "authorization_source": "RUNTIME_UPLOAD",
        "access_scope": "COMPANY_WIDE",
        "department": "HR",
    }
    assert runtime_upload_metadata_allowed(_user("HR"), metadata) is True
    assert runtime_upload_metadata_allowed(_user("ACCOUNTING"), metadata) is False


def test_runtime_filters_stay_within_chroma_predicate_quota() -> None:
    filters = _retrieval_filters(Settings(), _user("HR", UserRole.MANAGER))
    assert filters
    assert all(_predicate_leaf_count(where) <= 8 for where in filters)


def test_lifecycle_postcheck_rejects_future_and_expired_chunks() -> None:
    base = {
        "publication_status": "active",
        "artifact_state": "frozen",
        "retrieval_enabled": True,
    }
    assert (
        _metadata_lifecycle_allowed({**base, "effective_date_ymd": 20990101, "expiry_date_ymd": 99991231}, 20260823)
        is False
    )

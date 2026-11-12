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


def _user(department: str, role: UserRole = UserRole.EMPLOYEE) -> UserContext:
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


def test_company_wide_document_can_cross_department() -> None:
    engine = AuthorizationEngine()
    document = _document("HR", AccessScope.COMPANY_WIDE)
    assert engine.evaluate_access(_user("HR"), document) is True
    assert engine.evaluate_access(_user("PRODUCT"), document) is True


def test_super_admin_can_cross_department() -> None:
    engine = AuthorizationEngine()
    assert engine.evaluate_access(_user("HR", UserRole.SUPER_ADMIN), _document("PRODUCT")) is True


def test_runtime_company_wide_upload_is_visible_company_wide() -> None:
    metadata = {
        "authorization_source": "RUNTIME_UPLOAD",
        "access_scope": "COMPANY_WIDE",
        "department": "HR",
    }
    assert runtime_upload_metadata_allowed(_user("HR"), metadata) is True
    assert runtime_upload_metadata_allowed(_user("ACCOUNTING"), metadata) is True


def test_runtime_filters_stay_within_chroma_predicate_quota() -> None:
    filters = _retrieval_filters(Settings(), _user("HR", UserRole.DEPARTMENT_MANAGER))
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


def test_runtime_upload_metadata_cannot_override_registry_scope():
    """09/11: chunk Chroma của 13-QD-ABC ghi RUNTIME_UPLOAD + COMPANY_WIDE trong khi
    registry ghi DEPARTMENT/ACCOUNTING -> từng lộ cho nhân viên HR."""
    from src.security.authorization import runtime_upload_metadata_allowed
    from src.security.models import UserContext

    hr = UserContext.from_state({"tenant_id": "nexatech", "user_id": "u", "department": "HR", "user_role": "EMPLOYEE"})
    stale = {
        "source_file": "13-QD-ABC_Quy-Che-Chi-Tieu-Noi-Bo-Han-Muc-Duyet-Chi.docx",
        "authorization_source": "RUNTIME_UPLOAD",
        "access_scope": "COMPANY_WIDE",
        "department": "ACCOUNTING",
    }
    assert runtime_upload_metadata_allowed(hr, stale) is False
    # Upload thật (chưa vào registry) vẫn theo metadata runtime như cũ.
    assert runtime_upload_metadata_allowed(hr, {**stale, "source_file": "new_upload_not_in_registry.pdf"}) is True

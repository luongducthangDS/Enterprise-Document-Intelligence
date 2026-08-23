import json
import os
from functools import lru_cache
from typing import Any

from src.security.departments import canonical_department
from src.security.models import (
    AccessScope,
    DocumentDomain,
    DocumentSecurityProfile,
    UserContext,
    UserRole,
)


def runtime_upload_access_filters(user: UserContext) -> list[dict]:
    """One Chroma predicate per runtime grant, keeping every query under quota."""
    combined = runtime_upload_access_condition(user)
    runtime, department, grants = combined["$and"]
    return [{"$and": [runtime, department, grant]} for grant in grants["$or"]]


def _role_policy_allows_scope(policies: dict, role: str, scope: str) -> bool:
    """Role này được roles_policy cấp scope đó không?

    Runtime predicate và registry ACL phải dùng cùng một nguồn sự thật là
    access_policies.json — tránh một layer hào phóng hơn layer kia.
    Role lạ/không cấu hình → False (fail-closed).
    """
    role_cfg = (policies.get("roles_policy") or {}).get(role) or {}
    scopes = role_cfg.get("allowed_scopes") or []
    return "*" in scopes or scope in scopes


def runtime_upload_access_condition(user: UserContext) -> dict:
    """Build a fail-closed ACL predicate; department is mandatory for every scope."""
    runtime = {"authorization_source": "RUNTIME_UPLOAD"}
    role = user.role.value if isinstance(user.role, UserRole) else str(user.role).upper()
    department = {"department": canonical_department(user.department)}

    # Grants được gate theo roles_policy — cùng một nguồn sự thật với registry
    # ACL (evaluate_access). Role không được policy cấp scope thì không có
    # grant tương ứng, kể cả khi department khớp.
    policies = get_authorization_engine().policies
    grants: list[dict] = []
    if _role_policy_allows_scope(policies, role, AccessScope.COMPANY_WIDE.value):
        grants.append({"access_scope": AccessScope.COMPANY_WIDE.value})
    if _role_policy_allows_scope(policies, role, AccessScope.DEPARTMENT.value):
        grants.append({"access_scope": AccessScope.DEPARTMENT.value})
    if _role_policy_allows_scope(policies, role, AccessScope.ROLE.value):
        grants.append(
            {
                "$and": [
                    {"access_scope": AccessScope.ROLE.value},
                    {"authorized_role": role},
                ]
            }
        )
    # Người tải lên luôn đọc lại được tài liệu RESTRICTED của chính mình để
    # kiểm tra kết quả ingestion. Upload yêu cầu HR_ADMIN+ nên grant này trên
    # thực tế chỉ áp cho admin.
    grants.append(
        {
            "$and": [
                {"access_scope": AccessScope.RESTRICTED.value},
                {"owner_user_id": user.user_id},
            ]
        }
    )
    return {"$and": [runtime, department, {"$or": grants}]}


def runtime_upload_metadata_allowed(user: UserContext, metadata: dict[str, Any]) -> bool:
    """Evaluate runtime-upload ACL for candidates fetched outside query filters."""
    if metadata.get("authorization_source") != "RUNTIME_UPLOAD":
        return False

    if canonical_department(metadata.get("department")) != canonical_department(user.department):
        return False
    role = user.role.value if isinstance(user.role, UserRole) else str(user.role).upper()
    scope = str(metadata.get("access_scope", "")).upper().strip()
    policies = get_authorization_engine().policies
    if scope == AccessScope.COMPANY_WIDE.value:
        return _role_policy_allows_scope(policies, role, AccessScope.COMPANY_WIDE.value)
    if scope == AccessScope.DEPARTMENT.value:
        return _role_policy_allows_scope(policies, role, AccessScope.DEPARTMENT.value) and str(
            metadata.get("department", "")
        ).upper().strip() == user.department.upper().strip()
    if scope == AccessScope.ROLE.value:
        if not _role_policy_allows_scope(policies, role, AccessScope.ROLE.value):
            return False
        authorized_role = metadata.get("authorized_role", "")
        if isinstance(authorized_role, list):
            return role in {str(value).upper().strip() for value in authorized_role}
        return role == str(authorized_role).upper().strip()
    if scope == AccessScope.RESTRICTED.value:
        return str(metadata.get("owner_user_id", "")) == user.user_id
    return False


class AuthorizationEngine:
    """Enterprise Authorization Engine.

    Quyết định quyền truy xuất tài liệu của người dùng dựa trên mô hình:
    - Role-Based Access Control (RBAC)
    - Attribute-Based Access Control (ABAC)
    - Enterprise Policy Configuration (config/access_policies.json)
    """

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or os.path.join("config", "access_policies.json")
        self.policies = self._load_policies()

    def _load_policies(self) -> dict[str, Any]:
        """Tải cấu hình chính sách từ file JSON hoặc dùng fallback an toàn."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[auth] Cảnh báo: Không đọc được file policy ({e}), dùng default.")

        # Fallback an toàn (fail-closed)
        return {
            "roles_policy": {
                "EMPLOYEE": {
                    "allowed_scopes": ["COMPANY_WIDE", "DEPARTMENT"],
                    "allowed_domains": ["COMPANY_POLICY"],
                    "allow_cross_department": False,
                },
                "ADMIN": {"allowed_scopes": ["*"], "allowed_domains": ["*"], "allow_cross_department": True},
            },
            "domain_policies": {
                "LEGAL": {"allowed_roles": ["LEGAL_COUNSEL", "ADMIN"], "departments_with_access": []},
                "EXTERNAL_REFERENCE": {"allowed_roles": ["ADMIN"]},
            },
        }

    def reload(self) -> None:
        """Nạp lại chính sách cấu hình khi có thay đổi."""
        self.policies = self._load_policies()

    def evaluate_access(self, user: UserContext, doc: DocumentSecurityProfile) -> bool:
        """Đánh giá quyền truy cập: User có được truy xuất Document không?"""
        domain_str = doc.domain.value if isinstance(doc.domain, DocumentDomain) else str(doc.domain)
        scope_str = doc.access_scope.value if isinstance(doc.access_scope, AccessScope) else str(doc.access_scope)
        user_role_str = user.role.value if isinstance(user.role, UserRole) else str(user.role)
        user_dept = canonical_department(user.department)

        # 0. Loại bỏ hoàn toàn System / Internal Data khỏi User Knowledge Retrieval
        if not doc.is_knowledge_doc or domain_str in (
            DocumentDomain.EVALUATION_DATA.value,
            DocumentDomain.USER_PERSONA.value,
            DocumentDomain.SYSTEM_CONFIGURATION.value,
            DocumentDomain.OTHER.value,
        ):
            return False

        domain_policies = self.policies.get("domain_policies", {})
        # Department isolation is the outer boundary. Roles can only narrow it.
        if canonical_department(doc.department) != user_dept:
            return False

        if user.role == UserRole.ADMIN or "admin" in user.permissions:
            return True

        # 2. Xử lý domain EXTERNAL_REFERENCE (Mặc định bị chặn cho nhân viên thông thường)
        if domain_str == DocumentDomain.EXTERNAL_REFERENCE.value:
            ext_policy = domain_policies.get("EXTERNAL_REFERENCE", {})
            allowed_roles = [str(r).upper() for r in ext_policy.get("allowed_roles", ["ADMIN"])]
            return user_role_str in allowed_roles

        # 3. Xử lý domain LEGAL (Mặc định PENDING_BUSINESS_DECISION; chỉ cho phép nếu role hoặc phòng ban được Admin cấu hình CẤP QUYỀN THỰC TẾ)
        if domain_str == DocumentDomain.LEGAL.value:
            legal_policy = domain_policies.get("LEGAL", {})
            allowed_roles = [str(r).upper() for r in legal_policy.get("allowed_roles", ["ADMIN"])]
            if user_role_str in allowed_roles:
                return True

            depts_with_access = [str(d).upper() for d in legal_policy.get("departments_with_access", [])]
            if user_dept in depts_with_access or "ALL" in depts_with_access:
                doc_auth_depts = [str(d).upper() for d in doc.authorized_departments]
                if user_dept in doc_auth_depts or "ALL" in doc_auth_depts:
                    return True

            return False

        # 4. Kiểm tra trạng thái PENDING_REVIEW (Fail-closed)
        if scope_str == AccessScope.PENDING_REVIEW.value or doc.authorization_status == "PENDING_REVIEW":
            return False

        # 5. Kiểm tra theo cấu hình vai trò (roles_policy)
        roles_policy = self.policies.get("roles_policy", {})
        role_cfg = roles_policy.get(user_role_str)
        if not role_cfg:
            # Role không nằm trong chính sách: từ chối (fail-closed). Trước đây
            # fallback cấp COMPANY_WIDE cho role lạ — trái least-privilege.
            return False

        allowed_scopes = role_cfg.get("allowed_scopes", [])
        allowed_domains = role_cfg.get("allowed_domains", [])

        if "*" not in allowed_domains and domain_str not in allowed_domains:
            return False

        if "*" in allowed_scopes:
            return True

        if scope_str == AccessScope.COMPANY_WIDE.value:
            return "COMPANY_WIDE" in allowed_scopes

        # DEPARTMENT Scope: BẮT BUỘC Department AND Role (Chính xác theo yêu cầu)
        if scope_str == AccessScope.DEPARTMENT.value:
            if "DEPARTMENT" not in allowed_scopes:
                return False

            # Điều kiện 1: Department match
            doc_auth_depts = [str(d).upper() for d in doc.authorized_departments]
            doc_dept = canonical_department(doc.department)
            dept_matches = user_dept in doc_auth_depts or (not doc_auth_depts and user_dept == doc_dept)
            if not dept_matches:
                return False

            # Điều kiện 2: Role match
            doc_auth_roles = [str(r).upper() for r in doc.authorized_roles]
            role_matches = user_role_str in doc_auth_roles or "ALL" in doc_auth_roles or not doc_auth_roles
            if not role_matches:
                return False

            return True

        if scope_str == AccessScope.ROLE.value:
            if "ROLE" not in allowed_scopes:
                return False
            doc_auth_roles = [str(r).upper() for r in doc.authorized_roles]
            return user_role_str in doc_auth_roles

        if scope_str == AccessScope.RESTRICTED.value:
            return "RESTRICTED" in allowed_scopes

        return False

    def get_authorized_source_files(
        self,
        user: UserContext,
        registry_rows: list[Any] | None = None,
        include_disabled: bool = False,
    ) -> list[str]:
        """Trả về danh sách source_file được phép truy xuất cho User hiện tại."""
        if registry_rows is None:
            from src.ingestion.metadata import load_registry

            # HR/core và Product được ingest song song. Product có registry
            # riêng nên authorization phải hợp nhất các registry hiện có;
            # thiếu một file không được làm chết toàn bộ retrieval.
            registry_rows = []
            for registry_path in (
                "data/metadata/document_registry.csv",
                "data/metadata/accounting_document_registry.csv",
                "data/metadata/product_document_registry.csv",
            ):
                if os.path.exists(registry_path):
                    registry_rows.extend(load_registry(registry_path))

        allowed_files: list[str] = []
        for r in registry_rows:
            if not include_disabled:
                if not getattr(r, "retrieval_enabled", True) or getattr(r, "publication_status", "active") != "active":
                    continue

            domain_val = getattr(r, "document_domain", "COMPANY_POLICY")
            try:
                domain = DocumentDomain(domain_val)
            except ValueError:
                domain = DocumentDomain.OTHER

            scope_val = getattr(r, "access_scope", "COMPANY_WIDE")
            try:
                scope = AccessScope(scope_val)
            except ValueError:
                scope = AccessScope.COMPANY_WIDE

            # Parse related_departments (Semantic only)
            raw_rel = getattr(r, "related_departments", "[]")
            parsed_rel = []
            if isinstance(raw_rel, list):
                parsed_rel = [str(d).upper().strip() for d in raw_rel]
            elif isinstance(raw_rel, str):
                try:
                    parsed_rel = [str(d).upper().strip() for d in json.loads(raw_rel)]
                except Exception:
                    parsed_rel = [d.upper().strip() for d in raw_rel.split(",") if d.strip()]

            # Parse authorized_departments (Actual authorization)
            raw_auth_depts = getattr(r, "authorized_departments", "[]")
            parsed_auth_depts = []
            if isinstance(raw_auth_depts, list):
                parsed_auth_depts = [str(d).upper().strip() for d in raw_auth_depts]
            elif isinstance(raw_auth_depts, str):
                try:
                    parsed_auth_depts = [str(d).upper().strip() for d in json.loads(raw_auth_depts)]
                except Exception:
                    parsed_auth_depts = [d.upper().strip() for d in raw_auth_depts.split(",") if d.strip()]

            # Parse authorized_roles (Actual authorization)
            raw_auth_roles = getattr(r, "authorized_roles", "[]")
            parsed_auth_roles = []
            if isinstance(raw_auth_roles, list):
                parsed_auth_roles = [str(rl).upper().strip() for rl in raw_auth_roles]
            elif isinstance(raw_auth_roles, str):
                try:
                    parsed_auth_roles = [str(rl).upper().strip() for rl in json.loads(raw_auth_roles)]
                except Exception:
                    parsed_auth_roles = [rl.upper().strip() for rl in raw_auth_roles.split(",") if rl.strip()]

            is_knowledge = domain in (
                DocumentDomain.COMPANY_POLICY,
                DocumentDomain.DEPARTMENT_PROCESS,
                DocumentDomain.LEGAL,
                DocumentDomain.MANAGEMENT,
                DocumentDomain.EXTERNAL_REFERENCE,
            )

            doc_profile = DocumentSecurityProfile(
                source_file=r.source_file,
                domain=domain,
                department=getattr(r, "department", "GENERAL"),
                related_departments=parsed_rel,
                access_scope=scope,
                authorized_departments=parsed_auth_depts,
                authorized_roles=parsed_auth_roles,
                authorization_status=getattr(r, "authorization_status", "ACTIVE"),
                authorization_source=getattr(r, "authorization_source", "BUSINESS_POLICY"),
                classification_source=getattr(r, "classification_source", "DETERMINISTIC_AUDIT"),
                is_official=getattr(r, "is_official_policy", True),
                is_knowledge_doc=is_knowledge,
            )

            if self.evaluate_access(user, doc_profile):
                allowed_files.append(r.source_file)

        return allowed_files


@lru_cache(maxsize=1)
def get_authorization_engine(config_path: str | None = None) -> AuthorizationEngine:
    """Singleton AuthorizationEngine instance."""
    return AuthorizationEngine(config_path=config_path)

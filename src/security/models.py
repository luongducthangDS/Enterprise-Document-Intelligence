from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """Vai trò người dùng trong hệ sinh thái doanh nghiệp."""
    EMPLOYEE = "EMPLOYEE"                  # Nhân viên thông thường
    MANAGER = "MANAGER"                    # Quản lý cấp trung / Trưởng phòng
    DEPARTMENT_USER = "DEPARTMENT_USER"    # Nhân viên nghiệp vụ theo phòng ban
    HR_OPERATOR = "HR_OPERATOR"            # Chuyên viên nhân sự
    LEGAL_COUNSEL = "LEGAL_COUNSEL"        # Pháp chế / Luật sư doanh nghiệp
    FINANCE_OFFICER = "FINANCE_OFFICER"    # Chuyên viên tài chính / Kế toán
    EXECUTIVE = "EXECUTIVE"                # Ban giám đốc / C-Level
    ADMIN = "ADMIN"                        # Quản trị viên hệ thống


class DocumentDomain(str, Enum):
    """Phân loại bản chất nội dung tài liệu (Document Classification)."""
    # 1. Knowledge Documents (Tài liệu tri thức doanh nghiệp)
    COMPANY_POLICY = "COMPANY_POLICY"          # Chính sách / Quy chế chính thức toàn công ty
    DEPARTMENT_PROCESS = "DEPARTMENT_PROCESS"  # Quy trình SOP vận hành nội bộ phòng ban
    LEGAL = "LEGAL"                            # Văn bản quy phạm pháp luật nhà nước
    MANAGEMENT = "MANAGEMENT"                  # Quyết định điều hành & Biên bản họp lãnh đạo
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"  # Tài liệu tham khảo ngoài / Template
    # 2. System / Internal Data (Loại hoàn toàn khỏi Knowledge Retrieval & Citation)
    EVALUATION_DATA = "EVALUATION_DATA"        # Bộ dữ liệu đánh giá mô hình / Benchmark
    USER_PERSONA = "USER_PERSONA"              # Dữ liệu Persona thử nghiệm
    SYSTEM_CONFIGURATION = "SYSTEM_CONFIGURATION" # Cấu hình logic ứng dụng (vd: ticket routing)
    OTHER = "OTHER"                            # Dữ liệu nội bộ khác


class AccessScope(str, Enum):
    """Phạm vi quyền truy cập tài liệu (Permission / Access Control)."""
    COMPANY_WIDE = "COMPANY_WIDE"      # Áp dụng cho toàn bộ cán bộ nhân viên
    DEPARTMENT = "DEPARTMENT"          # Giới hạn trong phòng ban sở hữu / được cấp quyền
    ROLE = "ROLE"                      # Giới hạn theo vai trò cụ thể
    RESTRICTED = "RESTRICTED"          # Hạn chế cao (Ban lãnh đạo / Bảo mật)
    PENDING_REVIEW = "PENDING_REVIEW"  # Chưa xác định consumer -> Fail-closed
    CUSTOM = "CUSTOM"                  # Chính sách tùy biến theo nhóm quyền


class SensitivityLevel(str, Enum):
    """Mức độ bảo mật thông tin."""
    PUBLIC = "PUBLIC"              # Công khai
    INTERNAL = "INTERNAL"          # Nội bộ công ty
    CONFIDENTIAL = "CONFIDENTIAL"  # Bảo mật
    RESTRICTED = "RESTRICTED"      # Tối mật / Giới hạn nghiêm ngặt


class UserContext(BaseModel):
    """Ngữ cảnh định danh và phân quyền của người dùng khi truy vấn."""
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    department: str = Field(..., min_length=1)
    role: UserRole
    groups: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "UserContext":
        """Khởi tạo UserContext từ LangGraph AgentState (tin cậy từ auth session)."""
        required = ("tenant_id", "user_id", "department", "user_role")
        missing = [field for field in required if not str(state.get(field) or "").strip()]
        if missing:
            raise ValueError(f"Missing authenticated identity fields: {', '.join(missing)}")

        role_raw = str(state["user_role"]).upper().strip()
        role_aliases = {"SUPER_ADMIN": "ADMIN", "HR_ADMIN": "ADMIN"}
        try:
            role = UserRole(role_aliases.get(role_raw, role_raw))
        except ValueError as exc:
            raise ValueError(f"Unsupported authenticated role: {role_raw}") from exc

        dept = str(state["department"]).upper().strip()
        user_id = str(state["user_id"]).strip()
        tenant_id = str(state["tenant_id"]).strip().lower()
        groups = state.get("groups") or []
        permissions = state.get("permissions") or []

        return cls(
            tenant_id=tenant_id,
            user_id=user_id,
            department=dept,
            role=role,
            groups=groups,
            permissions=permissions,
        )



class DocumentSecurityProfile(BaseModel):
    """Hồ sơ bảo mật và phân quyền của tài liệu."""
    source_file: str
    domain: DocumentDomain = DocumentDomain.COMPANY_POLICY
    department: str = "GENERAL"
    related_departments: list[str] = Field(default_factory=list, description="Semantic relevance recommendation only. KHÔNG cấp quyền.")
    access_scope: AccessScope = AccessScope.COMPANY_WIDE
    authorized_departments: list[str] = Field(default_factory=list, description="Danh sách phòng ban được doanh nghiệp CẤP QUYỀN thực tế.")
    authorized_roles: list[str] = Field(default_factory=list, description="Danh sách vai trò được doanh nghiệp CẤP QUYỀN thực tế.")
    authorized_groups: list[str] = Field(default_factory=list)
    authorization_status: str = "ACTIVE"  # ACTIVE | PENDING_REVIEW | SUSPENDED | ARCHIVED
    authorization_source: str = "BUSINESS_POLICY"
    classification_source: str = "DETERMINISTIC_AUDIT"
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    is_official: bool = True
    is_knowledge_doc: bool = True



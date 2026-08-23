from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Department(StrEnum):
    HR = "HR"
    PRODUCT = "Product"
    ENGINEERING = "Engineering"
    IT = "IT"
    FINANCE = "Finance"
    ACCOUNTING = "Accounting"
    SALES = "Sales"
    MARKETING = "Marketing"
    OPERATIONS = "Operations"
    LEGAL = "Legal"


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    department: Department = Field(..., description="Department must use a supported canonical value")
    full_name: str | None = None
    role: str | None = Field(
        default=None,
        description="Vai trò tự đăng ký; chỉ chấp nhận employee/department_user — vai trò quản trị phải do SUPER_ADMIN cấp",
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserDTO(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    department: str

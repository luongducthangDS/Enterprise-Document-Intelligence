from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


REGISTRATION_DEPARTMENTS = {
    "HR",
    "PRODUCT",
    "ACCOUNTING",
}


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(..., min_length=8, description="Mật khẩu tối thiểu 8 ký tự")
    full_name: str | None = None
    department: str

    @field_validator("department")
    @classmethod
    def validate_department(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in REGISTRATION_DEPARTMENTS:
            raise ValueError("Phòng ban không hợp lệ")
        return normalized


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

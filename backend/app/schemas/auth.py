from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Department(str, Enum):
    HR = "HR"
    PRODUCT = "Product"
    ENGINEERING = "Engineering"
    IT = "IT"
    FINANCE = "Finance"
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

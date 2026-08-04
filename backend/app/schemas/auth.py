from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserDTO(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    department: str

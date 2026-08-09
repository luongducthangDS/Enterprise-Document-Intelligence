from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.auth import LoginRequest, RefreshTokenRequest, RegisterRequest
from app.schemas.common import wrap_response
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    register_req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Đăng ký tài khoản người dùng mới (Mặc định vai trò EMPLOYEE)."""
    user_dto = await AuthService.register_user(db, register_req)
    return wrap_response(user_dto.model_dump(), request)


@router.post("/login")
async def login(
    login_req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Xác thực người dùng & cấp phát JWT Access Token / Refresh Token."""
    token_resp = await AuthService.login(db, login_req)
    return wrap_response(token_resp.model_dump(), request)


@router.post("/refresh")
async def refresh_token(
    refresh_req: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Sử dụng Refresh Token để làm mới Access Token & Refresh Token."""
    token_resp = await AuthService.refresh_access_token(db, refresh_req.refresh_token)
    return wrap_response(token_resp.model_dump(), request)


@router.get("/me")
async def get_me(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lấy thông tin người dùng hiện tại từ JWT Token."""
    user = await AuthService.get_user_by_email(db, current_user["email"])
    if not user:
        user_dto = {
            "id": current_user["user_id"],
            "email": current_user["email"],
            "full_name": "User",
            "role": current_user["role"],
            "department": current_user["department"],
        }
    else:
        user_dto = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.profile.display_name if user.profile else "User",
            "role": user.profile.role if user.profile else current_user["role"],
            "department": user.profile.department if user.profile else current_user["department"],
        }
    return wrap_response(user_dto, request)

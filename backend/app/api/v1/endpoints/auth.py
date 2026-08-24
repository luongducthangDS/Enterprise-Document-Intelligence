from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.core.rate_limit import login_rate_limit_check, login_rate_limit_record
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
    """Create a public.users row and its matching public.profiles row."""
    user_dto = await AuthService.register_user(db, register_req)
    return wrap_response(user_dto.model_dump(), request)


@router.post("/login")
async def login(
    login_req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Authenticate against public.users and issue backend JWT tokens."""
    login_rate_limit_check(login_req.email, request)
    try:
        token_resp = await AuthService.login(db, login_req)
    except Exception:
        login_rate_limit_record(login_req.email, request)
        raise
    return wrap_response(token_resp.model_dump(), request)


@router.post("/refresh")
async def refresh_token(
    refresh_req: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    token_resp = await AuthService.refresh_access_token(db, refresh_req.refresh_token)
    return wrap_response(token_resp.model_dump(), request)


@router.get("/me")
async def get_me(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    email = current_user["email"] or ""
    user_dto = {
        "id": current_user["user_id"],
        "email": email,
        "full_name": current_user.get("full_name") or email.split("@")[0] or "User",
        "role": current_user["role"],
        "department": current_user["department"],
    }
    return wrap_response(user_dto, request)

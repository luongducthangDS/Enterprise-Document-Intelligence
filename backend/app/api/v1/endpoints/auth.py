from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.auth import LoginRequest, RefreshTokenRequest, RegisterRequest, TokenResponse, UserDTO
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=UserDTO, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserDTO:
    """Đăng ký tài khoản người dùng mới (Mặc định vai trò EMPLOYEE)."""
    return await AuthService.register_user(db, request)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Xác thực người dùng & cấp phát JWT Access Token / Refresh Token."""
    return await AuthService.login(db, request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Sử dụng Refresh Token để làm mới Access Token & Refresh Token."""
    return await AuthService.refresh_access_token(db, request.refresh_token)


@router.get("/me", response_model=UserDTO)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserDTO:
    """Lấy thông tin người dùng hiện tại từ JWT Token."""
    user = await AuthService.get_user_by_email(db, current_user["email"])
    if not user:
        return UserDTO(
            id=current_user["user_id"],
            email=current_user["email"],
            full_name="User",
            role=current_user["role"],
            department=current_user["department"],
        )
    return UserDTO(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        department=user.department,
    )

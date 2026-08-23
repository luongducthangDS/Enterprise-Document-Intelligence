import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.exceptions import AppException, AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserDTO

settings = get_settings()

# Vai trò được phép tự chọn khi đăng ký. Vai trò quản trị (hr_admin/
# super_admin) chỉ được cấp bởi SUPER_ADMIN qua trang Phân quyền — trigger
# prevent_self_privilege_escalation (migration 0003) là lớp chặn thứ hai.
SELF_REGISTRATION_ROLES = frozenset({"employee", "department_user"})


class AuthService:
    @classmethod
    async def get_user_by_email(cls, db: AsyncSession, email: str) -> UserDB | None:
        stmt = select(UserDB).options(joinedload(UserDB.profile)).where(UserDB.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def authenticate_user(cls, db: AsyncSession, email: str, password: str) -> UserDB:
        user = await cls.get_user_by_email(db, email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        return user

    @classmethod
    async def register_user(cls, db: AsyncSession, register_data: RegisterRequest) -> UserDTO:
        if await cls.get_user_by_email(db, register_data.email):
            raise AppException(
                status_code=400,
                code="EMAIL_ALREADY_REGISTERED",
                message="Email is already registered",
            )

        requested_role = (register_data.role or "employee").strip().lower()
        if requested_role not in SELF_REGISTRATION_ROLES:
            raise AppException(
                status_code=422,
                code="ROLE_NOT_ALLOWED_FOR_SIGNUP",
                message=(
                    "Vai trò này không thể tự đăng ký. Vai trò quản trị chỉ do "
                    "Quản trị hệ thống cấp sau khi tài khoản được tạo."
                ),
            )

        new_user = UserDB(
            email=register_data.email,
            hashed_password=hash_password(register_data.password),
        )
        new_user.profile = ProfileDB(
            display_name=register_data.full_name or register_data.email.split("@")[0],
            role=requested_role,
            employment_status="full_time",
            department=register_data.department.value,
            contract_type="khong_xac_dinh_thoi_han",
            access_level="self_only",
        )
        db.add(new_user)
        await db.commit()

        user = await cls.get_user_by_email(db, register_data.email)
        assert user is not None and user.profile is not None
        return UserDTO(
            id=str(user.id),
            email=user.email,
            full_name=user.profile.display_name,
            role=user.profile.role.upper(),
            department=user.profile.department or "",
        )

    @classmethod
    async def login(cls, db: AsyncSession, login_data: LoginRequest) -> TokenResponse:
        user = await cls.authenticate_user(db, login_data.email, login_data.password)
        role = (user.profile.role if user.profile else "employee").upper()
        department = user.profile.department if user.profile else ""
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "full_name": user.profile.display_name if user.profile else user.email.split("@")[0],
                "role": role,
                "department": department,
            }
        )
        refresh_token = create_refresh_token(data={"sub": str(user.id), "email": user.email})
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    @classmethod
    async def refresh_access_token(cls, db: AsyncSession, refresh_token_str: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token_str)
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Refresh token has expired") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid refresh token") from exc

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type. Expected refresh token")
        email = payload.get("email")
        if not email:
            raise AuthenticationError("Invalid token payload")

        user = await cls.get_user_by_email(db, email)
        if not user:
            raise AuthenticationError("User associated with token no longer exists")

        role = (user.profile.role if user.profile else "employee").upper()
        department = user.profile.department if user.profile else ""
        return TokenResponse(
            access_token=create_access_token(
                data={
                    "sub": str(user.id),
                    "email": user.email,
                    "full_name": user.profile.display_name if user.profile else user.email.split("@")[0],
                    "role": role,
                    "department": department,
                }
            ),
            refresh_token=create_refresh_token(data={"sub": str(user.id), "email": user.email}),
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

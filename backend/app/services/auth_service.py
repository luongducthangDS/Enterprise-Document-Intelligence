import uuid

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException, AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.domain.models.user import UserDB
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserDTO

settings = get_settings()


class AuthService:
    @classmethod
    async def get_user_by_email(cls, db: AsyncSession, email: str) -> UserDB | None:
        stmt = select(UserDB).where(UserDB.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def authenticate_user(cls, db: AsyncSession, email: str, password: str) -> UserDB:
        user = await cls.get_user_by_email(db, email)
        if not user:
            raise AuthenticationError("Invalid email or password")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        return user

    @classmethod
    async def register_user(cls, db: AsyncSession, register_data: RegisterRequest) -> UserDTO:
        existing_user = await cls.get_user_by_email(db, register_data.email)
        if existing_user:
            raise AppException(
                status_code=400,
                code="EMAIL_ALREADY_REGISTERED",
                message="Email is already registered",
            )

        hashed_pwd = hash_password(register_data.password)
        full_name = register_data.full_name or register_data.email.split("@")[0]

        new_user = UserDB(
            id=uuid.uuid4(),
            email=register_data.email,
            hashed_password=hashed_pwd,
            role="EMPLOYEE",
            department=register_data.department,
            full_name=full_name,
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        return UserDTO(
            id=str(new_user.id),
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            department=new_user.department,
        )

    @classmethod
    async def login(cls, db: AsyncSession, login_data: LoginRequest) -> TokenResponse:
        user = await cls.authenticate_user(db, login_data.email, login_data.password)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "department": user.department,
        }
        access_token = create_access_token(data=payload)
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
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Refresh token has expired")
        except jwt.PyJWTError:
            raise AuthenticationError("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type. Expected refresh token")

        email = payload.get("email")
        if not email:
            raise AuthenticationError("Invalid token payload")

        user = await cls.get_user_by_email(db, email)
        if not user:
            raise AuthenticationError("User associated with token no longer exists")

        new_access_payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "department": user.department,
        }
        new_access_token = create_access_token(data=new_access_payload)
        new_refresh_token = create_refresh_token(data={"sub": str(user.id), "email": user.email})

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

import uuid

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.db_deps import get_db
from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.security import decode_token
from app.domain.models.profile import ProfileDB

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate JWT, then reload authorization attributes from ProfileDB (SoT)."""
    if not token:
        raise AuthenticationError("Token is required")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token") from exc
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type. Expected access token")
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid authenticated subject") from exc
    profile = await db.get(ProfileDB, user_id)
    if profile is None:
        raise AuthenticationError("Authenticated profile no longer exists")
    role = str(profile.role or "").upper().strip()
    department = str(profile.department or "").strip()
    if not role or not department:
        raise AuthenticationError("Authenticated profile is incomplete")
    return {
        "user_id": str(user_id),
        "email": payload.get("email"),
        "full_name": profile.display_name,
        "role": role,
        "department": department,
    }


def require_role(allowed_roles: list[str]):
    normalized_roles = {role.upper() for role in allowed_roles}

    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in normalized_roles:
            raise ForbiddenError("You do not have permission to access this resource.")
        return current_user

    return role_checker
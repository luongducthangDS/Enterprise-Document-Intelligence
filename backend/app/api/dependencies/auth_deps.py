import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Validate JWT access token và trả về thông tin user."""
    if not token:
        raise AuthenticationError("Token is required")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Access token has expired")
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid access token")

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type. Expected access token")

    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role"),
        "department": payload.get("department"),
    }


def require_role(allowed_roles: list[str]):
    """Dependency factory kiểm tra quyền truy cập RBAC."""

    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise ForbiddenError("You do not have permission to access this resource.")
        return current_user

    return role_checker

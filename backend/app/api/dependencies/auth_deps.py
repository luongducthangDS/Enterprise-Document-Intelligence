import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Validate the backend JWT access token and return its user claims."""
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
    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": str(payload.get("role") or "EMPLOYEE").upper(),
        "department": payload.get("department"),
    }


def require_role(allowed_roles: list[str]):
    normalized_roles = {role.upper() for role in allowed_roles}

    async def role_checker(current_user: dict = Depends(get_current_user)):
        if str(current_user.get("role") or "").upper() not in normalized_roles:
            raise ForbiddenError("You do not have permission to access this resource.")
        return current_user

    return role_checker

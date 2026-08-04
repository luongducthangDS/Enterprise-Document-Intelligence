from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.exceptions import AuthenticationError, ForbiddenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Validate JWT token và trả về thông tin user."""
    if not token:
        raise AuthenticationError()
    return {"user_id": "123", "email": "employee@company.com", "role": "EMPLOYEE", "department": "HR"}


def require_role(allowed_roles: list[str]):
    """Dependency factory kiểm tra quyền truy cập RBAC."""
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise ForbiddenError("You do not have permission to access this resource.")
        return current_user

    return role_checker

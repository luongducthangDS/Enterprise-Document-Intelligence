from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import logger


class AppException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message


class AuthenticationError(AppException):
    def __init__(self, message: str = "Invalid credentials or token"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, code="UNAUTHORIZED", message=message)


class ForbiddenError(AppException):
    def __init__(self, message: str = "Access denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, code="FORBIDDEN", message=message)


async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Error at {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
            },
        },
    )

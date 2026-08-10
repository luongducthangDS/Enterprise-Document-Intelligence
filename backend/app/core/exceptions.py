import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import logger


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        retryable: bool = False,
        retry_after_ms: int | None = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms


class AuthenticationError(AppException):
    def __init__(self, message: str = "Invalid credentials or token", code: str = "UNAUTHORIZED"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
            message=message,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Access denied", code: str = "FORBIDDEN"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            message=message,
        )


class NotFoundError(AppException):
    def __init__(self, code: str = "NOT_FOUND", message: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code=code,
            message=message,
        )


class ConflictError(AppException):
    def __init__(self, code: str = "CONFLICT", message: str = "Resource conflict"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            message=message,
        )


def _get_request_id(request: Request) -> str:
    return getattr(getattr(request, "state", None), "request_id", None) or f"req_{uuid.uuid4().hex[:12]}"


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = _get_request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "request_id": request_id,
            "success": False,
            "data": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "retryable": exc.retryable,
                "retry_after_ms": exc.retry_after_ms,
            },
            "meta": {
                "timestamp": datetime.now(UTC).isoformat(),
                "api_version": "v1",
            },
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = _get_request_id(request)
    details = [
        {
            "field": ".".join(str(loc) for loc in error.get("loc", []) if loc != "body"),
            "message": error.get("msg", ""),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "request_id": request_id,
            "success": False,
            "data": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Dữ liệu không hợp lệ.",
                "details": details,
                "retryable": False,
                "retry_after_ms": None,
            },
            "meta": {
                "timestamp": datetime.now(UTC).isoformat(),
                "api_version": "v1",
            },
        },
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled Error at {request.url.path}: {exc}", exc_info=True)
    request_id = _get_request_id(request)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "request_id": request_id,
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected server error occurred.",
                "details": None,
                "retryable": True,
                "retry_after_ms": 1000,
            },
            "meta": {
                "timestamp": datetime.now(UTC).isoformat(),
                "api_version": "v1",
            },
        },
    )

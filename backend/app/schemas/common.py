import uuid
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from fastapi import Request
from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    api_version: str = "v1"
    pagination: dict[str, Any] | None = None


class ErrorDetailItem(BaseModel):
    field: str | None = None
    message: str


class APIError(BaseModel):
    code: str
    message: str
    details: list[ErrorDetailItem] | list[dict[str, Any]] | None = None
    retryable: bool = False
    retry_after_ms: int | None = None


class StandardResponse(BaseModel, Generic[T]):
    request_id: str
    success: bool
    data: T | None = None
    error: APIError | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


def wrap_response(
    data: Any = None,
    request: Request | None = None,
    pagination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tạo response bọc dữ liệu chuẩn theo quy ước apiBackend.md."""
    req_id = getattr(getattr(request, "state", None), "request_id", None) or f"req_{uuid.uuid4().hex[:12]}"
    meta: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "api_version": "v1",
    }
    if pagination is not None:
        meta["pagination"] = pagination

    return {
        "request_id": req_id,
        "success": True,
        "data": data,
        "error": None,
        "meta": meta,
    }

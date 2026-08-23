"""Rate limiting in-memory cho endpoint xác thực (chống brute-force login).

Thiết kế cho pilot single-process: sliding window theo (email, IP). Khi chuyển
sang multi-worker/multi-instance cần thay backend lưu trữ bằng Redis — interface
giữ nguyên để đổi chỗ dễ.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from app.core.exceptions import AppException

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300.0

_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _client_ip(request) -> str:
    forwarded = request.headers.get("x-forwarded-for") if request else None
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


def login_rate_limit_check(email: str, request) -> None:
    """Ném 429 nếu (email, IP) vượt quá ngưỡng thử trong cửa sổ 5 phút.

    Gọi TRƯỚC khi verify mật khẩu; ghi nhận lượt thử bằng
    login_rate_limit_record khi xác thực thất bại (đăng nhập đúng thì không ghi).
    """
    key = f"{(email or '').strip().lower()}|{_client_ip(request)}"
    now = time.monotonic()
    with _lock:
        window = _attempts[key]
        while window and now - window[0] > _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= _MAX_ATTEMPTS:
            retry_after = int(_WINDOW_SECONDS - (now - window[0])) + 1
            raise AppException(
                status_code=429,
                code="TOO_MANY_LOGIN_ATTEMPTS",
                message=f"Quá nhiều lần đăng nhập sai. Vui lòng thử lại sau {retry_after} giây.",
                retryable=True,
                retry_after_ms=retry_after * 1000,
            )


def login_rate_limit_record(email: str, request) -> None:
    """Ghi nhận một lần đăng nhập thất bại vào cửa sổ."""
    key = f"{(email or '').strip().lower()}|{_client_ip(request)}"
    with _lock:
        _attempts[key].append(time.monotonic())


def login_rate_limit_reset_for_tests() -> None:
    """Xóa trạng thái limiter giữa các bài test."""
    with _lock:
        _attempts.clear()

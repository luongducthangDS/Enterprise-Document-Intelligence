"""Rate limiting in-memory cho endpoint xác thực (chống brute-force login).

Thiết kế cho pilot single-process: sliding window theo (email, IP). Khi chuyển
sang multi-worker/multi-instance cần thay backend lưu trữ bằng Redis — interface
giữ nguyên để đổi chỗ dễ.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from app.core.config import get_settings
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


# ponytail: đếm trong RAM nên reset khi restart và X-Forwarded-For giả mạo được;
# trần toàn cục mới là giới hạn cứng cho quota. Cần chặt hơn thì chuyển sang Redis.
_HOUR = 3600.0
_DAY = 86400.0
_DEMO_SESSIONS_PER_IP_HOUR = 20
_DEMO_SESSIONS_PER_DAY = 300
_DEMO_CHATS_PER_IP_HOUR = 30
_DEMO_CHATS_PER_DAY = 300


def _consume(key: str, limit: int, window_seconds: float, message: str) -> None:
    """Ghi nhận một lượt vào cửa sổ trượt; ném 429 nếu đã hết hạn mức."""
    now = time.monotonic()
    with _lock:
        window = _attempts[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= limit:
            retry_after = int(window_seconds - (now - window[0])) + 1
            raise AppException(
                status_code=429,
                code="DEMO_LIMIT_REACHED",
                message=message,
                retryable=True,
                retry_after_ms=retry_after * 1000,
            )
        window.append(now)


def demo_session_limit(request: Request) -> None:
    message = "Bản demo đang nhận quá nhiều phiên mới. Vui lòng thử lại sau."
    _consume(f"demo-session|{_client_ip(request)}", _DEMO_SESSIONS_PER_IP_HOUR, _HOUR, message)
    _consume("demo-session|all", _DEMO_SESSIONS_PER_DAY, _DAY, message)


def demo_chat_limit(request: Request) -> None:
    """Chỉ áp dụng khi DEMO_MODE bật; môi trường thường không bị giới hạn."""
    if not get_settings().demo_mode:
        return
    message = "Bạn đã dùng hết lượt hỏi của bản demo. Vui lòng thử lại sau."
    _consume(f"demo-chat|{_client_ip(request)}", _DEMO_CHATS_PER_IP_HOUR, _HOUR, message)
    _consume("demo-chat|all", _DEMO_CHATS_PER_DAY, _DAY, message)


def login_rate_limit_reset_for_tests() -> None:
    """Xóa trạng thái limiter giữa các bài test."""
    with _lock:
        _attempts.clear()

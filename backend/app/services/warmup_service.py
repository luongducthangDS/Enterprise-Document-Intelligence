"""WarmupService: Quản lý việc đánh thức Agent Service khi Backend được wakeup.

Cơ chế:
- Được gọi từ endpoint /health của Backend.
- Khi FE ping /health → Backend trả 200 ngay lập tức + fire-and-forget ping Agent /health.
- Debounce 5 phút: nếu Agent vừa được ping gần đây → bỏ qua, không spam.
- Chỉ kích hoạt khi APP_ENV == production.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from app.core.config import get_settings
from app.core.logging import logger

_settings = get_settings()

# Thời gian debounce: không ping lại Agent trong vòng 5 phút kể từ lần ping cuối
_DEBOUNCE_SECONDS = 300.0

_last_wakeup_time: float = 0.0
_wakeup_lock = asyncio.Lock()


def _agent_health_url() -> str:
    """Chuyển đổi AI_AGENT_SERVICE_URL sang /health URL của Agent.

    Ví dụ: https://agent.onrender.com/api/v1/agent → https://agent.onrender.com/health
    """
    base = _settings.ai_agent_service_url
    return base.split("/api/v1")[0].rstrip("/") + "/health"


async def fire_agent_wakeup() -> None:
    """Kích hoạt đánh thức Agent ngầm (fire-and-forget).

    Hàm này không block caller — nó tạo một asyncio task riêng và trả về ngay.
    Chỉ thực sự gửi ping khi:
      1. APP_ENV == production
      2. Chưa ping trong vòng 5 phút gần đây (debounce)
    """
    if _settings.app_env != "production":
        return
    if not _settings.ai_agent_service_url:
        return

    asyncio.create_task(_do_wakeup())


async def _do_wakeup() -> None:
    """Thực hiện vòng polling đánh thức Agent cho đến khi nhận được HTTP 200."""
    global _last_wakeup_time

    async with _wakeup_lock:
        now = time.monotonic()
        if now - _last_wakeup_time < _DEBOUNCE_SECONDS:
            logger.debug(
                f"[WarmupService] Agent đã được đánh thức gần đây "
                f"({now - _last_wakeup_time:.0f}s trước). Bỏ qua."
            )
            return
        _last_wakeup_time = now

    health_url = _agent_health_url()
    logger.info(f"[WarmupService] 🚀 Bắt đầu đánh thức Agent tại {health_url}...")

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(1, 16):  # tối đa ~70s (14 lần x 5s)
            try:
                res = await client.get(health_url)
                if res.status_code == 200:
                    logger.info(
                        f"[WarmupService] ✅ Agent sẵn sàng sau {attempt} lần thử!"
                    )
                    return
                logger.debug(
                    f"[WarmupService] Agent trả về {res.status_code} "
                    f"(lần {attempt}/15) — đang chờ khởi động..."
                )
            except Exception as exc:
                logger.debug(
                    f"[WarmupService] Chưa kết nối được tới Agent "
                    f"(lần {attempt}/15): {type(exc).__name__}"
                )
            await asyncio.sleep(5.0)

    logger.warning("[WarmupService] ⚠️ Agent không phản hồi sau 70s.")

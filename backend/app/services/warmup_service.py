import asyncio
import httpx
from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


class WarmupService:
    """Service kiểm tra sức khỏe và đánh thức (Warmup) Agent Service từ Backend."""

    # Event loop chỉ giữ weak reference tới task: không lưu lại thì task có thể bị
    # GC trước khi kịp chạy, và tín hiệu đánh thức biến mất im lặng.
    _background_tasks: set[asyncio.Task] = set()

    @classmethod
    async def check_and_warmup_on_startup(cls, max_wait_seconds: float = 30.0) -> bool:
        """Chạy đúng 1 lần duy nhất trong Startup Lifespan của Backend.
        Thăm dò /health tới Agent Service để đảm bảo Agent đã sẵn sàng trước khi nhận traffic.
        """
        base_url = settings.ai_agent_service_url.rstrip("/").split("/api/v1")[0]
        health_url = f"{base_url}/health"
        logger.info(f"[Startup Lifespan] 🔍 Đang kiểm tra kết nối tới AI Agent tại {health_url}...")

        start_time = asyncio.get_event_loop().time()
        timeout = 5.0

        async with httpx.AsyncClient(timeout=timeout) as client:
            while (asyncio.get_event_loop().time() - start_time) < max_wait_seconds:
                try:
                    res = await client.get(health_url)
                    if res.status_code == 200:
                        elapsed = asyncio.get_event_loop().time() - start_time
                        logger.info(f"[Startup Lifespan] ✅ AI Agent Service đã SẴN SÀNG (phản hồi sau {elapsed:.2f}s)!")
                        return True
                except Exception as e:
                    logger.debug(f"[Startup Lifespan] Đang đợi Agent Service khởi động: {e}")
                await asyncio.sleep(2.0)

        logger.warning(
            f"[Startup Lifespan] ⚠️ AI Agent Service chưa phản hồi sau {max_wait_seconds}s (sẽ tự động đánh thức khi có request)."
        )
        return False

    @classmethod
    def trigger_background_warmup(cls) -> None:
        """Kích hoạt tác vụ bất đồng bộ đánh thức Agent trong background khi có lỗi timeout/mất kết nối."""
        async def _ping():
            base_url = settings.ai_agent_service_url.rstrip("/").split("/api/v1")[0]
            health_url = f"{base_url}/health"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.get(health_url)
                    logger.info(f"[WarmupService] 🔔 Đã gửi tín hiệu đánh thức Agent tại {health_url}")
            except Exception as e:
                logger.debug(f"[WarmupService] Gửi tín hiệu đánh thức Agent thất bại: {e}")

        try:
            task = asyncio.create_task(_ping())
            cls._background_tasks.add(task)
            task.add_done_callback(cls._background_tasks.discard)
        except Exception as e:
            logger.debug(f"[WarmupService] Không thể tạo background task warmup: {e}")


async def fire_agent_wakeup() -> None:
    """Helper gọi nhanh trigger_background_warmup."""
    WarmupService.trigger_background_warmup()


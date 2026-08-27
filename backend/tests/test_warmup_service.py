import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.services.warmup_service import WarmupService


@pytest.mark.asyncio
async def test_warmup_service_success_on_startup():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=httpx.MockTransport(handler))):
        ready = await WarmupService.check_and_warmup_on_startup(max_wait_seconds=5.0)
        assert ready is True


@pytest.mark.asyncio
async def test_warmup_service_handles_agent_offline():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "unavailable"})

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=httpx.MockTransport(handler))):
        ready = await WarmupService.check_and_warmup_on_startup(max_wait_seconds=0.1)
        assert ready is False


@pytest.mark.asyncio
async def test_trigger_background_warmup_executes():
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200))) as mock_get:
        WarmupService.trigger_background_warmup()
        # Give event loop a cycle to run background task
        import asyncio
        await asyncio.sleep(0.05)
        assert mock_get.called

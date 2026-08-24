import hashlib
import hmac
import json
from collections.abc import AsyncIterator

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import logger
from app.schemas.agent import AgentAnswerDTO

settings = get_settings()

_IDENTITY_FIELDS = ("request_id", "user_id", "tenant_id", "department", "user_role")


def _identity_signature(payload: dict, secret: str) -> str:
    identity = {field: payload.get(field) for field in _IDENTITY_FIELDS}
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


class AIAgentClientError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class AIAgentClient:
    """REST API Client giao tiếp từ Backend Service sang AI Agent Core Service."""

    def __init__(
        self,
        base_url: str = settings.ai_agent_service_url,
        timeout: float = settings.ai_agent_timeout_seconds,
        service_token: str = settings.ai_agent_service_token,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.service_token = service_token
        self.transport = transport

    async def _wait_until_agent_ready(self, client: httpx.AsyncClient, max_wait_seconds: float = 50.0) -> bool:
        """Thăm dò endpoint /health liên tục cho tới khi container Agent tỉnh ngủ và trả về HTTP 200."""
        if self.transport is not None:
            return False
        import asyncio
        import time
        health_url = self.base_url.split("/api/v1")[0] + "/health"
        logger.info(f"[Render Cold-Start] Đang gửi tín hiệu và thăm dò đánh thức Agent tại {health_url} (tối đa {max_wait_seconds}s)...")
        start = time.time()
        while (time.time() - start) < max_wait_seconds:
            try:
                res = await client.get(health_url, timeout=8.0)
                if res.status_code == 200:
                    logger.info(f"[Render Cold-Start] ✅ Agent đã thức dậy và sẵn sàng (sau {time.time() - start:.1f}s)!")
                    return True
            except Exception as e:
                logger.debug(f"[Render Cold-Start] Đang chờ container khởi động: {e}")
            await asyncio.sleep(4.0)
        return False


    async def query_agent(
        self,
        user_id: str,
        query: str,
        department: str,
        request_id: str,
        user_role: str,
        tenant_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentAnswerDTO:
        payload = {
            "user_id": user_id,
            "query": query,
            "department": department,
            "user_role": user_role,
            "tenant_id": tenant_id,
            "request_id": request_id,
            "history": history or [],
        }
        headers = {"X-Request-ID": request_id}
        if self.service_token:
            headers["X-Service-Token"] = self.service_token
            headers["X-Identity-Signature"] = _identity_signature(payload, self.service_token)

        max_retries = 3
        last_exception = None

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            for attempt in range(1, max_retries + 1):
                try:
                    response = await client.post(f"{self.base_url}/query", json=payload, headers=headers)
                    response.raise_for_status()
                    return AgentAnswerDTO.model_validate(response.json())
                except httpx.HTTPStatusError as exc:
                    last_exception = exc
                    # Nếu gặp lỗi 502/503 (Render container đang ngủ / khởi động lại)
                    if exc.response.status_code in (502, 503) and attempt == 1:
                        logger.warning(
                            f"[AIAgentClient] Nhận HTTP {exc.response.status_code} từ Agent (Render Cold Start). Đang tự động đợi Agent tỉnh dậy..."
                        )
                        ready = await self._wait_until_agent_ready(client, max_wait_seconds=50.0)
                        if ready:
                            continue

                    retryable = exc.response.status_code >= 500
                    logger.error(f"AI Agent returned HTTP {exc.response.status_code}: {exc}")
                    raise AIAgentClientError(
                        "AGENT_SERVICE_ERROR", "AI Agent service returned an error", retryable
                    ) from exc
                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    last_exception = exc
                    if attempt == 1:
                        logger.warning(
                            f"[AIAgentClient] Lỗi kết nối/timeout tới Agent (Render Cold Start). Đang đợi Agent tỉnh dậy..."
                        )
                        ready = await self._wait_until_agent_ready(client, max_wait_seconds=50.0)
                        if ready:
                            continue
                    logger.error(f"AI Agent request timed out: {exc}")
                    raise AIAgentClientError("AGENT_TIMEOUT", "AI Agent request timed out") from exc
                except httpx.RequestError as exc:
                    logger.error(f"Failed to communicate with AI Agent Service: {exc}")
                    raise AIAgentClientError("AGENT_UNAVAILABLE", "AI Agent service is unavailable") from exc
                except (ValidationError, ValueError) as exc:
                    logger.error(f"AI Agent returned an invalid response: {exc}")
                    raise AIAgentClientError("AGENT_INVALID_RESPONSE", "AI Agent response is invalid", False) from exc

            if last_exception:
                raise AIAgentClientError("AGENT_SERVICE_ERROR", "AI Agent service returned an error after retries") from last_exception



    async def stream_query_agent(
        self,
        user_id: str,
        query: str,
        department: str,
        request_id: str,
        user_role: str,
        tenant_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict]:
        """Đọc SSE từ Agent Core và trả từng event đã parse cho ChatService."""
        payload = {
            "user_id": user_id,
            "query": query,
            "department": department,
            "user_role": user_role,
            "tenant_id": tenant_id,
            "request_id": request_id,
            "history": history or [],
        }
        headers = {"X-Request-ID": request_id, "Accept": "text/event-stream"}
        if self.service_token:
            headers["X-Service-Token"] = self.service_token
            headers["X-Identity-Signature"] = _identity_signature(payload, self.service_token)

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/query/stream",
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    seen_done = False
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:].strip())
                        except (json.JSONDecodeError, TypeError) as exc:
                            raise AIAgentClientError(
                                "AGENT_INVALID_RESPONSE",
                                "AI Agent stream contains invalid JSON",
                                False,
                            ) from exc
                        if not isinstance(event, dict) or not event.get("type"):
                            raise AIAgentClientError(
                                "AGENT_INVALID_RESPONSE",
                                "AI Agent stream contains an invalid event",
                                False,
                            )
                        seen_done = seen_done or event["type"] == "done"
                        yield event
                    if not seen_done:
                        raise AIAgentClientError(
                            "AGENT_INVALID_RESPONSE",
                            "AI Agent stream ended before the final result",
                            True,
                        )
            except AIAgentClientError:
                raise
            except httpx.TimeoutException as exc:
                logger.error(f"AI Agent stream timed out: {exc}")
                raise AIAgentClientError("AGENT_TIMEOUT", "AI Agent request timed out") from exc
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code >= 500
                logger.error(f"AI Agent stream returned HTTP {exc.response.status_code}: {exc}")
                raise AIAgentClientError(
                    "AGENT_SERVICE_ERROR", "AI Agent service returned an error", retryable
                ) from exc
            except httpx.RequestError as exc:
                logger.error(f"Failed to stream from AI Agent Service: {exc}")
                raise AIAgentClientError("AGENT_UNAVAILABLE", "AI Agent service is unavailable") from exc

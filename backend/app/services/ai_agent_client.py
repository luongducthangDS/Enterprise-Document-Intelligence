import json
from collections.abc import AsyncIterator

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import logger
from app.schemas.agent import AgentAnswerDTO

settings = get_settings()


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

    async def query_agent(
        self,
        user_id: str,
        query: str,
        department: str,
        request_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentAnswerDTO:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            try:
                payload = {
                    "user_id": user_id,
                    "query": query,
                    "department": department,
                    "request_id": request_id,
                    "history": history or [],
                }
                headers = {"X-Request-ID": request_id}
                if self.service_token:
                    headers["X-Service-Token"] = self.service_token
                response = await client.post(f"{self.base_url}/query", json=payload, headers=headers)
                response.raise_for_status()
                return AgentAnswerDTO.model_validate(response.json())
            except httpx.TimeoutException as exc:
                logger.error(f"AI Agent request timed out: {exc}")
                raise AIAgentClientError("AGENT_TIMEOUT", "AI Agent request timed out") from exc
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code >= 500
                logger.error(f"AI Agent returned HTTP {exc.response.status_code}: {exc}")
                raise AIAgentClientError(
                    "AGENT_SERVICE_ERROR", "AI Agent service returned an error", retryable
                ) from exc
            except httpx.RequestError as exc:
                logger.error(f"Failed to communicate with AI Agent Service: {exc}")
                raise AIAgentClientError("AGENT_UNAVAILABLE", "AI Agent service is unavailable") from exc
            except (ValidationError, ValueError) as exc:
                logger.error(f"AI Agent returned an invalid response: {exc}")
                raise AIAgentClientError("AGENT_INVALID_RESPONSE", "AI Agent response is invalid", False) from exc

    async def stream_query_agent(
        self,
        user_id: str,
        query: str,
        department: str,
        request_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict]:
        """Đọc SSE từ Agent Core và trả từng event đã parse cho ChatService."""
        payload = {
            "user_id": user_id,
            "query": query,
            "department": department,
            "request_id": request_id,
            "history": history or [],
        }
        headers = {"X-Request-ID": request_id, "Accept": "text/event-stream"}
        if self.service_token:
            headers["X-Service-Token"] = self.service_token

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

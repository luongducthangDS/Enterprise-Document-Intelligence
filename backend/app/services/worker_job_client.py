from typing import Any

import httpx

from app.core.config import get_settings


class WorkerJobClientError(RuntimeError):
    """Agent worker API is unavailable or returned an invalid response."""


class WorkerJobClient:
    """Small typed boundary for Backend -> Agent worker job calls."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        service_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ai_agent_service_url).rstrip("/")
        self.timeout = timeout or settings.ai_agent_timeout_seconds
        self.service_token = service_token if service_token is not None else settings.ai_agent_service_token
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {"X-Service-Token": self.service_token} if self.service_token else {}

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WorkerJobClientError(f"Agent worker request failed: {exc}") from exc
        if not isinstance(body, dict):
            raise WorkerJobClientError("Agent worker returned a non-object response")
        return body

    async def submit_ingestion(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/jobs/ingestion", payload)

    async def submit_document_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/jobs/document-analysis", payload)

    async def submit_index_rebuild(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/jobs/index-rebuild", payload)

    async def submit_evaluation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/jobs/evaluation", payload)

    async def get_status(self, job_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/jobs/{job_id}")

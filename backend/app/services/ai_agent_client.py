from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


class AIAgentClient:
    """REST API Client giao tiếp từ Backend Service sang AI Agent Core Service."""

    def __init__(
        self, base_url: str = settings.ai_agent_service_url, timeout: float = settings.ai_agent_timeout_seconds
    ):
        self.base_url = base_url
        self.timeout = timeout

    async def query_agent(self, user_id: str, query: str, department: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    "user_id": user_id,
                    "query": query,
                    "department_context": department,
                }
                response = await client.post(f"{self.base_url}/query", json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                logger.error(f"Failed to communicate with AI Agent Service: {exc}")
                raise

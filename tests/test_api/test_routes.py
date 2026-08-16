from unittest.mock import AsyncMock, patch

import pytest

from src.config import get_settings
from src.models.schemas import AgentAnswer


def service_headers() -> dict[str, str]:
    token = get_settings().agent_service_token
    return {"X-Service-Token": token} if token else {}


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    response = await client.post("/api/v1/chat", json={"message": ""}, headers=service_headers())
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_legacy_chat_rejects_invalid_service_token(client):
    settings = type("Settings", (), {"agent_service_token": "expected-token"})()
    with patch("src.api.routes.get_settings", return_value=settings):
        response = await client.post(
            "/api/v1/chat",
            json={"message": "Leave policy"},
            headers={"X-Service-Token": "wrong-token"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_chat_redacts_client_facing_citation_metadata(client):
    answer = AgentAnswer(
        response="Safe answer",
        intent="hr_question",
        citations=[
            {
                "chunk_id": "policy::1",
                "source_file": "owner-hr@company.com.pdf",
                "title": "Contact 0912345678",
                "category": "leave",
                "is_official_policy": True,
            }
        ],
    )
    with patch("src.api.routes.agent_answer", new=AsyncMock(return_value=answer)):
        response = await client.post(
            "/api/v1/chat",
            json={"message": "Policy question"},
            headers=service_headers(),
        )

    assert response.status_code == 200
    citation = response.json()["citations"][0]
    assert "hr@company.com" not in citation["source_file"]
    assert "0912345678" not in citation["title"]


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200

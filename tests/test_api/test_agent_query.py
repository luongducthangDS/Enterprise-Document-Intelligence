from unittest.mock import AsyncMock, patch

import pytest

from src.models.schemas import AgentAnswer


@pytest.mark.asyncio
async def test_internal_agent_query_returns_agent_answer(client):
    answer = AgentAnswer(
        response="Policy answer",
        intent="hr_question",
        confidence_score=0.91,
        citations=[],
    )
    payload = {
        "query": "How many leave days do I have?",
        "request_id": "req-123",
        "user_id": "user-123",
        "department": "Engineering",
    }

    with patch("src.api.routes.agent_answer", new=AsyncMock(return_value=answer)) as mocked:
        response = await client.post("/api/v1/agent/query", json=payload)

    assert response.status_code == 200
    assert response.json()["response"] == "Policy answer"
    mocked.assert_awaited_once_with(payload["query"])


@pytest.mark.asyncio
async def test_internal_agent_query_validates_required_trace_fields(client):
    response = await client.post("/api/v1/agent/query", json={"query": "Leave policy"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_internal_agent_query_rejects_invalid_service_token(client):
    settings = type("Settings", (), {"agent_service_token": "expected-token"})()
    payload = {
        "query": "Leave policy",
        "request_id": "req-123",
        "user_id": "user-123",
        "department": "Engineering",
    }
    with patch("src.api.routes.get_settings", return_value=settings):
        response = await client.post(
            "/api/v1/agent/query",
            json=payload,
            headers={"X-Service-Token": "wrong-token"},
        )
    assert response.status_code == 401

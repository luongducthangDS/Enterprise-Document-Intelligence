import json
from unittest.mock import AsyncMock, patch

import pytest

from src.config import get_settings
from src.models.schemas import AgentAnswer


def service_headers() -> dict[str, str]:
    token = get_settings().agent_service_token
    return {"X-Service-Token": token} if token else {}


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
        "history": [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ],
    }

    with patch("src.api.routes.agent_answer", new=AsyncMock(return_value=answer)) as mocked:
        response = await client.post("/api/v1/agent/query", json=payload, headers=service_headers())

    assert response.status_code == 200
    assert response.json()["response"] == "Policy answer"
    mocked.assert_awaited_once_with(payload["query"], history=payload["history"])


@pytest.mark.asyncio
async def test_internal_agent_query_returns_citation_excerpt(client):
    answer = AgentAnswer(
        response="Policy answer",
        intent="hr_question",
        citations=[
            {
                "chunk_id": "policy::0001",
                "source_file": "policy.md",
                "title": "Leave policy",
                "category": "leave",
                "is_official_policy": True,
                "excerpt": "Employees receive 12 leave days per year.",
            }
        ],
    )
    payload = {
        "query": "How many leave days do I have?",
        "request_id": "req-excerpt-123",
        "user_id": "user-123",
        "department": "Engineering",
    }

    with patch("src.api.routes.agent_answer", new=AsyncMock(return_value=answer)):
        response = await client.post("/api/v1/agent/query", json=payload, headers=service_headers())

    assert response.status_code == 200
    assert response.json()["citations"][0]["excerpt"] == "Employees receive 12 leave days per year."


@pytest.mark.asyncio
async def test_internal_agent_query_keeps_history_optional(client):
    answer = AgentAnswer(response="Hello", intent="greeting", citations=[])
    payload = {
        "query": "Hello",
        "request_id": "req-124",
        "user_id": "user-123",
        "department": "Engineering",
    }

    with patch("src.api.routes.agent_answer", new=AsyncMock(return_value=answer)) as mocked:
        response = await client.post("/api/v1/agent/query", json=payload, headers=service_headers())

    assert response.status_code == 200
    mocked.assert_awaited_once_with("Hello", history=[])


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


@pytest.mark.asyncio
async def test_internal_agent_query_streams_sse_events(client):
    async def fake_stream(query, history=None):
        assert query == "Leave policy"
        assert history == []
        yield {"type": "status", "value": "Đang tìm trong tài liệu HR..."}
        yield {
            "type": "done",
            "answer": AgentAnswer(response="Policy answer", intent="hr_question").model_dump(),
        }

    payload = {
        "query": "Leave policy",
        "request_id": "req-stream",
        "user_id": "user-123",
        "department": "Engineering",
    }
    with patch("src.api.routes.agent_stream_answer", new=fake_stream):
        response = await client.post("/api/v1/agent/query/stream", json=payload, headers=service_headers())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    payloads = [
        json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert [item["type"] for item in payloads] == ["status", "done"]
    assert payloads[-1]["answer"]["response"] == "Policy answer"

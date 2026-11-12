import json

import httpx
import pytest
from app.services.ai_agent_client import AIAgentClient, AIAgentClientError


def agent_response() -> dict:
    return {
        "response": "Policy answer",
        "intent": "hr_question",
        "confidence_score": 0.9,
        "citations": [],
        "needs_clarification": False,
        "clarifying_question": None,
        "escalate": False,
        "escalate_reason": None,
        "ticket_draft": None,
    }


@pytest.mark.asyncio
async def test_client_sends_internal_contract_and_parses_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/api/v1/agent/query"
        assert request.headers["X-Service-Token"] == "secret"
        assert request.headers["X-Request-ID"] == "request-1"
        assert request.headers["X-Identity-Signature"]
        assert payload == {
            "user_id": "user-1",
            "query": "Leave policy",
            "department": "Engineering",
            "user_role": "EMPLOYEE",
            "tenant_id": "nexatech",
            "request_id": "request-1",
            "history": [
                {"role": "user", "content": "Previous question"},
                {"role": "assistant", "content": "Previous answer"},
            ],
        }
        return httpx.Response(200, json=agent_response())

    client = AIAgentClient(
        base_url="http://agent/api/v1/agent/",
        service_token="secret",
        transport=httpx.MockTransport(handler),
    )
    result = await client.query_agent(
        "user-1",
        "Leave policy",
        "Engineering",
        "request-1",
        user_role="EMPLOYEE",
        tenant_id="nexatech",
        history=[
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ],
    )
    assert result.response == "Policy answer"
    assert result.confidence_score == 0.9


@pytest.mark.asyncio
async def test_client_maps_timeout_to_typed_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = AIAgentClient(base_url="http://agent", transport=httpx.MockTransport(handler))
    with pytest.raises(AIAgentClientError) as error:
        await client.query_agent("user-1", "Leave policy", "Engineering", "request-1", "EMPLOYEE", "nexatech")

    assert error.value.code == "AGENT_TIMEOUT"
    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_client_rejects_invalid_agent_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "missing intent"})

    client = AIAgentClient(base_url="http://agent", transport=httpx.MockTransport(handler))
    with pytest.raises(AIAgentClientError) as error:
        await client.query_agent("user-1", "Leave policy", "Engineering", "request-1", "EMPLOYEE", "nexatech")

    assert error.value.code == "AGENT_INVALID_RESPONSE"
    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_client_parses_agent_sse_stream():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/query/stream"
        body = "".join(
            [
                'event: status\ndata: {"type":"status","value":"Đang tìm..."}\n\n',
                f"event: done\ndata: {json.dumps({'type': 'done', 'answer': agent_response()})}\n\n",
            ]
        )
        return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})

    client = AIAgentClient(base_url="http://agent", transport=httpx.MockTransport(handler))
    events = [
        event
        async for event in client.stream_query_agent(
            "user-1",
            "Leave policy",
            "Engineering",
            "request-stream",
            "EMPLOYEE",
            "nexatech",
        )
    ]

    assert [event["type"] for event in events] == ["status", "done"]
    assert events[-1]["answer"]["response"] == "Policy answer"


@pytest.mark.asyncio
async def test_client_retries_on_502_cold_start():
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, text="Bad Gateway (cold start)")
        body = "".join(
            [
                'event: status\ndata: {"type":"status","value":"Đang soạn..."}\n\n',
                f"event: done\ndata: {json.dumps({'type': 'done', 'answer': agent_response()})}\n\n",
            ]
        )
        return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})

    client = AIAgentClient(
        base_url="http://agent",
        transport=httpx.MockTransport(handler),
        max_cold_retries=3,
        cold_retry_delay=0.01,
    )
    events = [
        event
        async for event in client.stream_query_agent(
            "user-1",
            "Leave policy",
            "Engineering",
            "request-cold",
            "EMPLOYEE",
            "nexatech",
        )
    ]

    assert attempts == 2
    # First yielded event should be the cold start status
    assert events[0]["type"] == "status"
    assert "cold start" in events[0]["value"]
    assert events[-1]["type"] == "done"


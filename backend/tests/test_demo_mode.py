import pytest
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.rate_limit import _DEMO_CHATS_PER_IP_HOUR, demo_chat_limit, login_rate_limit_reset_for_tests
from starlette.requests import Request

from tests.conftest import client


@pytest.fixture(autouse=True)
def _reset_limits():
    login_rate_limit_reset_for_tests()
    yield
    login_rate_limit_reset_for_tests()


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", True)


def _request() -> Request:
    return Request({"type": "http", "headers": [], "client": ("1.2.3.4", 1)})


def test_demo_session_is_hidden_when_demo_mode_off():
    assert client.post("/api/v1/auth/demo", json={"department": "HR"}).status_code == 404


def test_each_demo_session_is_a_separate_employee(demo_on):
    users = []
    for _ in range(2):
        response = client.post("/api/v1/auth/demo", json={"department": "PRODUCT"})
        assert response.status_code == 201
        token = response.json()["data"]["access_token"]
        users.append(client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["data"])
    assert users[0]["id"] != users[1]["id"]
    assert all(user["role"] == "EMPLOYEE" and user["department"] == "PRODUCT" for user in users)


def test_demo_session_rejects_unknown_department(demo_on):
    assert client.post("/api/v1/auth/demo", json={"department": "EXECUTIVE"}).status_code == 422


def test_chat_limit_blocks_after_quota_only_in_demo_mode(demo_on):
    for _ in range(_DEMO_CHATS_PER_IP_HOUR):
        demo_chat_limit(_request())
    with pytest.raises(AppException) as error:
        demo_chat_limit(_request())
    assert error.value.status_code == 429


def test_chat_limit_is_off_outside_demo_mode():
    for _ in range(_DEMO_CHATS_PER_IP_HOUR + 1):
        demo_chat_limit(_request())

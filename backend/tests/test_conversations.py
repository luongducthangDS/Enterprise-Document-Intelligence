import uuid

import pytest
import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.messages import MessageDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB

from tests.conftest import TestingSessionLocal, client


async def ensure_user_and_profile(session, user_id, email, display_name, department):
    user = await session.get(UserDB, user_id)
    if not user:
        user = UserDB(
            id=user_id,
            email=email,
            hashed_password=hash_password("password123"),
        )
        session.add(user)
        await session.flush()

    profile = await session.get(ProfileDB, user_id)
    if not profile:
        profile = ProfileDB(
            id=user_id,
            display_name=display_name,
            role="EMPLOYEE",
            department=department,
        )
        session.add(profile)
        await session.flush()


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_conversations_test_data():
    async with TestingSessionLocal() as session:
        user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        other_user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        await ensure_user_and_profile(session, user_id, "user1@company.com", "User One", "Engineering")
        await ensure_user_and_profile(session, other_user_id, "user2@company.com", "User Two", "Marketing")

        await session.commit()


def get_auth_header(user_id: str = "11111111-1111-1111-1111-111111111111", email: str = "user1@company.com") -> dict:
    payload = {
        "sub": user_id,
        "email": email,
        "role": "EMPLOYEE",
        "department": "Engineering",
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


def test_create_conversation_endpoint():
    headers = get_auth_header()
    response = client.post(
        "/api/v1/conversations",
        json={"title": "Hỏi về chế độ nghỉ phép"},
        headers=headers,
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["success"] is True
    assert "conversation_id" in res_data["data"]
    assert res_data["data"]["title"] == "Hỏi về chế độ nghỉ phép"
    assert res_data["data"]["state"] == "ACTIVE"


def test_create_conversation_default_title():
    headers = get_auth_header()
    response = client.post("/api/v1/conversations", json={"title": None}, headers=headers)
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["data"]["title"] == "Hội thoại mới"


def test_list_conversations_only_returns_current_user_items():
    user1_headers = get_auth_header("11111111-1111-1111-1111-111111111111", "user1@company.com")
    user2_headers = get_auth_header("22222222-2222-2222-2222-222222222222", "user2@company.com")

    user1_response = client.post(
        "/api/v1/conversations",
        json={"title": "Conversation history user 1"},
        headers=user1_headers,
    )
    user2_response = client.post(
        "/api/v1/conversations",
        json={"title": "Conversation history user 2"},
        headers=user2_headers,
    )

    response = client.get("/api/v1/conversations", headers=user1_headers)
    assert response.status_code == 200
    items = response.json()["data"]
    item_ids = {item["conversation_id"] for item in items}
    assert user1_response.json()["data"]["conversation_id"] in item_ids
    assert user2_response.json()["data"]["conversation_id"] not in item_ids
    assert all("message_count" in item and "last_message_at" in item for item in items)


def test_rename_conversation_endpoint():
    headers = get_auth_header()
    create_resp = client.post("/api/v1/conversations", json={"title": None}, headers=headers)
    conv_id = create_resp.json()["data"]["conversation_id"]

    response = client.patch(
        f"/api/v1/conversations/{conv_id}",
        json={"title": "Chính sách nghỉ phép"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["title"] == "Chính sách nghỉ phép"


def test_delete_conversation_hides_it_without_removing_audit_data():
    headers = get_auth_header()
    create_resp = client.post("/api/v1/conversations", json={"title": "Conversation to delete"}, headers=headers)
    conv_id = create_resp.json()["data"]["conversation_id"]

    response = client.delete(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == {"conversation_id": conv_id, "deleted": True}

    listed = client.get("/api/v1/conversations", headers=headers).json()["data"]
    assert all(item["conversation_id"] != conv_id for item in listed)

    response_again = client.delete(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert response_again.status_code == 404


def test_get_conversation_info_endpoint():
    headers = get_auth_header()
    create_resp = client.post("/api/v1/conversations", json={"title": "Hội thoại test GET"}, headers=headers)
    conv_id = create_resp.json()["data"]["conversation_id"]

    response = client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["conversation_id"] == conv_id
    assert res_data["data"]["title"] == "Hội thoại test GET"
    assert res_data["data"]["message_count"] == 0


def test_get_conversation_not_found():
    headers = get_auth_header()
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/conversations/{fake_id}", headers=headers)
    assert response.status_code == 404
    res_data = response.json()
    assert res_data["success"] is False
    assert res_data["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_get_conversation_forbidden():
    user1_headers = get_auth_header("11111111-1111-1111-1111-111111111111", "user1@company.com")
    user2_headers = get_auth_header("22222222-2222-2222-2222-222222222222", "user2@company.com")

    create_resp = client.post("/api/v1/conversations", json={"title": "Private Conv User 1"}, headers=user1_headers)
    conv_id = create_resp.json()["data"]["conversation_id"]

    response = client.get(f"/api/v1/conversations/{conv_id}", headers=user2_headers)
    assert response.status_code == 403
    res_data = response.json()
    assert res_data["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_conversation_messages_endpoint():
    headers = get_auth_header()
    create_resp = client.post("/api/v1/conversations", json={"title": "Messages Conv"}, headers=headers)
    conv_id = create_resp.json()["data"]["conversation_id"]

    # Insert sample messages into DB
    async with TestingSessionLocal() as session:
        msg1 = MessageDB(
            id=uuid.uuid4(),
            conversation_id=uuid.UUID(conv_id),
            role="user",
            content="Quy định nghỉ phép năm như thế nào?",
        )
        msg2 = MessageDB(
            id=uuid.uuid4(),
            conversation_id=uuid.UUID(conv_id),
            role="assistant",
            content="Theo quy định, nhân viên được hưởng 12 ngày phép năm...",
            citations=[{"citation_id": "cit_01", "title": "Chính sách nghỉ phép", "page": 5}],
        )
        session.add_all([msg1, msg2])
        await session.commit()

    response = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert len(res_data["data"]["messages"]) == 2
    assert res_data["data"]["messages"][0]["role"] == "user"
    assert res_data["data"]["messages"][1]["citations"][0]["citation_id"] == "cit_01"
    assert "is_official_policy" in res_data["data"]["messages"][1]["citations"][0]
    assert "source_type" in res_data["data"]["messages"][1]["citations"][0]


def test_end_conversation_endpoint():
    headers = get_auth_header()
    create_resp = client.post("/api/v1/conversations", json={"title": "Conv to End"}, headers=headers)
    conv_id = create_resp.json()["data"]["conversation_id"]

    # End conversation
    response = client.post(f"/api/v1/conversations/{conv_id}/end", headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["state"] == "ENDED"
    assert res_data["data"]["ended_at"] is not None

    # Retry ending already ended conversation
    response_again = client.post(f"/api/v1/conversations/{conv_id}/end", headers=headers)
    assert response_again.status_code == 409
    res_data_again = response_again.json()
    assert res_data_again["error"]["code"] == "CONVERSATION_ENDED"

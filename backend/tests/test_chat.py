import uuid

import pytest
import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.conversations import ConversationDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.services.chat_service import ChatService

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
async def setup_chat_test_data():
    async with TestingSessionLocal() as session:
        user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        other_user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        await ensure_user_and_profile(session, user_id, "user1@company.com", "User One", "Engineering")
        await ensure_user_and_profile(session, other_user_id, "user2@company.com", "User Two", "Marketing")

        conv_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        conv = await session.get(ConversationDB, conv_id)
        if not conv:
            conv = ConversationDB(
                id=conv_id,
                user_id=user_id,
                title="Active Chat Session",
                state="ACTIVE",
            )
            session.add(conv)

        ended_conv_id = uuid.UUID("44444444-4444-4444-4444-444444444444")
        ended_conv = await session.get(ConversationDB, ended_conv_id)
        if not ended_conv:
            ended_conv = ConversationDB(
                id=ended_conv_id,
                user_id=user_id,
                title="Ended Session",
                state="ENDED",
            )
            session.add(ended_conv)

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


@pytest.mark.asyncio
async def test_submit_chat_request_success():
    headers = get_auth_header()
    conv_id = "33333333-3333-3333-3333-333333333333"
    question = "Nghỉ phép thai sản bao nhiêu tháng?"

    response = client.post(
        "/api/v1/chat/requests",
        json={"conversation_id": conv_id, "question": question},
        headers=headers,
    )
    assert response.status_code == 202
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["state"] == "QUEUED"
    assert "chat_request_id" in res_data["data"]

    chat_req_id = res_data["data"]["chat_request_id"]

    # Explicitly process background task
    await ChatService._process_chat_rag_request(
        chat_request_id=uuid.UUID(chat_req_id),
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        department="Engineering",
        question=question,
        conversation_id=uuid.UUID(conv_id),
    )

    # Poll status
    status_resp = client.get(f"/api/v1/chat/requests/{chat_req_id}", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["success"] is True
    assert status_data["data"]["state"] == "COMPLETED"
    assert status_data["data"]["answer"] is not None


@pytest.mark.asyncio
async def test_first_question_names_default_conversation():
    conversation_id = uuid.uuid4()
    user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    question = "  Chính sách   làm việc hybrid áp dụng như thế nào?  "
    async with TestingSessionLocal() as session:
        session.add(ConversationDB(
            id=conversation_id,
            user_id=user_id,
            title="Hội thoại mới",
            state="ACTIVE",
        ))
        await session.commit()
        await ChatService.submit_chat_request(
            session,
            user_id,
            "Engineering",
            conversation_id,
            question,
        )

    async with TestingSessionLocal() as session:
        conversation = await session.get(ConversationDB, conversation_id)
        assert conversation is not None
        assert conversation.title == "Chính sách làm việc hybrid áp dụng như thế nào?"


def test_submit_chat_request_ended_conversation():
    headers = get_auth_header()
    ended_conv_id = "44444444-4444-4444-4444-444444444444"

    response = client.post(
        "/api/v1/chat/requests",
        json={"conversation_id": ended_conv_id, "question": "Hỏi trong phiên đã ngắt"},
        headers=headers,
    )
    assert response.status_code == 409
    res_data = response.json()
    assert res_data["success"] is False
    assert res_data["error"]["code"] == "CONVERSATION_ENDED"


def test_submit_chat_request_accepts_more_than_2000_characters():
    headers = get_auth_header()
    conv_id = "33333333-3333-3333-3333-333333333333"
    previous_background_tasks_enabled = ChatService.background_tasks_enabled
    ChatService.background_tasks_enabled = False
    try:
        response = client.post(
            "/api/v1/chat/requests",
            json={"conversation_id": conv_id, "question": "a" * 2001},
            headers=headers,
        )
    finally:
        ChatService.background_tasks_enabled = previous_background_tasks_enabled

    assert response.status_code == 202


def test_get_chat_request_status_not_found():
    headers = get_auth_header()
    fake_id = str(uuid.uuid4())

    response = client.get(f"/api/v1/chat/requests/{fake_id}", headers=headers)
    assert response.status_code == 404
    res_data = response.json()
    assert res_data["error"]["code"] == "CHAT_REQUEST_NOT_FOUND"


def test_get_chat_request_status_forbidden():
    user1_headers = get_auth_header("11111111-1111-1111-1111-111111111111", "user1@company.com")
    user2_headers = get_auth_header("22222222-2222-2222-2222-222222222222", "user2@company.com")
    conv_id = "33333333-3333-3333-3333-333333333333"

    submit_resp = client.post(
        "/api/v1/chat/requests",
        json={"conversation_id": conv_id, "question": "Câu hỏi bảo mật"},
        headers=user1_headers,
    )
    chat_req_id = submit_resp.json()["data"]["chat_request_id"]

    response = client.get(f"/api/v1/chat/requests/{chat_req_id}", headers=user2_headers)
    assert response.status_code == 403
    res_data = response.json()
    assert res_data["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_retry_chat_request_success():
    headers = get_auth_header()
    conv_id = "33333333-3333-3333-3333-333333333333"
    question = "Câu hỏi này không có trong tài liệu"

    # Submit question that triggers REFUSED state ("không có trong tài liệu")
    submit_resp = client.post(
        "/api/v1/chat/requests",
        json={"conversation_id": conv_id, "question": question},
        headers=headers,
    )
    chat_req_id = submit_resp.json()["data"]["chat_request_id"]

    # Explicitly run background task to completion (sets state = REFUSED)
    await ChatService._process_chat_rag_request(
        chat_request_id=uuid.UUID(chat_req_id),
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        department="Engineering",
        question=question,
        conversation_id=uuid.UUID(conv_id),
    )

    # Retry request
    retry_resp = client.post(
        f"/api/v1/chat/requests/{chat_req_id}/retry",
        json={"reason": "USER_RETRY"},
        headers=headers,
    )
    assert retry_resp.status_code == 202
    retry_data = retry_resp.json()
    assert retry_data["success"] is True
    assert retry_data["data"]["parent_chat_request_id"] == chat_req_id
    assert "chat_request_id" in retry_data["data"]

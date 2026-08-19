import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.chat_requests import ChatRequestDB
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
async def setup_durability_test_data():
    async with TestingSessionLocal() as session:
        user_id = uuid.UUID("77777777-7777-7777-7777-777777777777")
        await ensure_user_and_profile(session, user_id, "durability_user@company.com", "Durability User", "IT")

        conv_id = uuid.UUID("88888888-8888-8888-8888-888888888888")
        conv = await session.get(ConversationDB, conv_id)
        if not conv:
            conv = ConversationDB(
                id=conv_id,
                user_id=user_id,
                title="Durability Test Conversation",
                state="ACTIVE",
            )
            session.add(conv)
        await session.commit()


def get_token_header() -> dict:
    payload = {
        "sub": "77777777-7777-7777-7777-777777777777",
        "email": "durability_user@company.com",
        "role": "EMPLOYEE",
        "department": "IT",
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


class TestChatJobDurabilityComprehensive:
    """Tác nhân 5 & 6: Kiểm thử toàn diện Chat Job Durability & Thẩm định QA Scenarios."""

    @pytest.mark.asyncio
    async def test_recover_pending_requests_recent_rescheduled(self):
        """Kịch bản 1: Request gần đây (<10 phút) bị gián đoạn do restart -> Tự động khôi phục QUEUED và chạy lại."""
        async with TestingSessionLocal() as session:
            req_id = uuid.uuid4()
            user_id = uuid.UUID("77777777-7777-7777-7777-777777777777")
            conv_id = uuid.UUID("88888888-8888-8888-8888-888888888888")

            req = ChatRequestDB(
                id=req_id,
                conversation_id=conv_id,
                user_id=user_id,
                question="Câu hỏi đang xử lý dở",
                state="GENERATING",
                created_at=datetime.now(UTC) - timedelta(minutes=2),
                updated_at=datetime.now(UTC) - timedelta(minutes=2),
            )
            session.add(req)
            await session.commit()

        # Bật background_tasks_enabled cho durability test
        ChatService.background_tasks_enabled = True
        try:
            with patch.object(ChatService, "_schedule_chat_request") as mock_schedule:
                recovered_count = await ChatService.recover_pending_requests()

            assert recovered_count >= 1
            mock_schedule.assert_called()

            # Kiểm tra trạng thái DB đã về QUEUED
            async with TestingSessionLocal() as session:
                saved = await session.get(ChatRequestDB, req_id)
                assert saved is not None
                assert saved.state == "QUEUED"
        finally:
            ChatService.background_tasks_enabled = False

    @pytest.mark.asyncio
    async def test_recover_pending_requests_timeout_marked_failed(self):
        """Kịch bản 2: Request cũ (>10 phút) bị kẹt lúc restart -> Đánh dấu FAILED với code WORKER_RESTARTED và retryable=True."""
        async with TestingSessionLocal() as session:
            req_id = uuid.uuid4()
            user_id = uuid.UUID("77777777-7777-7777-7777-777777777777")
            conv_id = uuid.UUID("88888888-8888-8888-8888-888888888888")

            old_time = datetime.now(UTC) - timedelta(minutes=15)
            req = ChatRequestDB(
                id=req_id,
                conversation_id=conv_id,
                user_id=user_id,
                question="Câu hỏi bị treo từ lâu",
                state="GENERATING",
                created_at=old_time,
                updated_at=old_time,
            )
            session.add(req)
            await session.commit()

        ChatService.background_tasks_enabled = True
        try:
            await ChatService.recover_pending_requests()

            async with TestingSessionLocal() as session:
                saved = await session.get(ChatRequestDB, req_id)
                assert saved is not None
                assert saved.state == "FAILED"
                assert saved.failure["code"] == "WORKER_RESTARTED"
                assert saved.retryable is True
        finally:
            ChatService.background_tasks_enabled = False

    @pytest.mark.asyncio
    async def test_cancel_background_tasks_on_shutdown(self):
        """Kịch bản 3: Thẩm định QA (Tác nhân 6) — Hủy task an toàn khi shutdown, không để task mồ côi."""
        async def dummy_coro():
            await asyncio.sleep(10)

        task = asyncio.create_task(dummy_coro())
        ChatService.background_tasks.add(task)

        await ChatService.cancel_background_tasks()

        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_chat_error_isolation_fails_gracefully(self):
        """Kịch bản 4: Thẩm định QA (Tác nhân 6) — Agent Client lỗi không làm crash background task."""
        async with TestingSessionLocal() as session:
            req_id = uuid.uuid4()
            user_id = uuid.UUID("77777777-7777-7777-7777-777777777777")
            conv_id = uuid.UUID("88888888-8888-8888-8888-888888888888")

            req = ChatRequestDB(
                id=req_id,
                conversation_id=conv_id,
                user_id=user_id,
                question="Câu hỏi gây lỗi LLM",
                state="QUEUED",
            )
            session.add(req)
            await session.commit()

        with patch.object(ChatService.agent_client, "query_agent", side_effect=Exception("LLM Gateway Timeout")):
            await ChatService._process_chat_rag_request(
                chat_request_id=req_id,
                user_id=user_id,
                department="IT",
                question="Câu hỏi gây lỗi LLM",
                conversation_id=conv_id,
            )

        async with TestingSessionLocal() as session:
            saved = await session.get(ChatRequestDB, req_id)
            assert saved is not None
            assert saved.state == "FAILED"
            assert saved.failure is not None
            assert saved.retryable is True

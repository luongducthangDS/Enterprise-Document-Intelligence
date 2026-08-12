import asyncio
import time
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.messages import MessageDB
from app.domain.models.profile import ProfileDB
from app.domain.models.ticket import TicketDB
from app.domain.models.user import UserDB
from app.services.chat_service import ChatService
from main import app

from tests.conftest import TestingSessionLocal


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
async def setup_e2e_test_data():
    # Bật chế độ tự động chạy background tasks của Backend như môi trường Production
    old_bg_setting = ChatService.background_tasks_enabled
    ChatService.background_tasks_enabled = True

    async with TestingSessionLocal() as session:
        user_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
        await ensure_user_and_profile(session, user_id, "e2e_user@company.com", "E2E User", "Engineering")

        conv_id = uuid.UUID("66666666-6666-6666-6666-666666666666")
        conv = await session.get(ConversationDB, conv_id)
        if not conv:
            conv = ConversationDB(
                id=conv_id,
                user_id=user_id,
                title="E2E Polling Recovery Test Session",
                state="ACTIVE",
            )
            session.add(conv)

        await session.commit()

    yield

    ChatService.background_tasks_enabled = old_bg_setting


def get_e2e_auth_header() -> dict:
    payload = {
        "sub": "55555555-5555-5555-5555-555555555555",
        "email": "e2e_user@company.com",
        "role": "EMPLOYEE",
        "department": "Engineering",
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


async def poll_until_terminal(async_client: AsyncClient, chat_req_id: str, headers: dict, timeout_seconds: float = 5.0) -> dict:
    """Helper poll tự động bất đồng bộ theo thời gian như client production."""
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout_seconds:
        resp = await async_client.get(f"/api/v1/chat/requests/{chat_req_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        if data["state"] in ("COMPLETED", "REFUSED", "CLARIFICATION_REQUIRED", "FAILED"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Chat request {chat_req_id} did not reach terminal state in {timeout_seconds}s")


@pytest.mark.asyncio
async def test_e2e_client_midway_disconnection_and_repoll_recovery():
    """Mô phỏng trường hợp backend tự động chạy background task như production.

    Client gửi request, tạm dừng poll (giả lập rớt mạng), sau đó re-poll lại và nhận kết quả tự động hoàn thành.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = get_e2e_auth_header()
        conv_id = "66666666-6666-6666-6666-666666666666"
        question = "Thời gian thử việc tối đa là bao nhiêu tháng?"

        # 1. Client gửi yêu cầu hỏi-đáp RAG (Backend tự động kích hoạt background task)
        response = await ac.post(
            "/api/v1/chat/requests",
            json={"conversation_id": conv_id, "question": question},
            headers=headers,
        )
        assert response.status_code == 202
        res_data = response.json()
        assert res_data["success"] is True
        chat_req_id = res_data["data"]["chat_request_id"]
        assert res_data["data"]["state"] == "QUEUED"

        # 2. Client kiểm tra trạng thái ban đầu
        poll_1 = await ac.get(f"/api/v1/chat/requests/{chat_req_id}", headers=headers)
        assert poll_1.status_code == 200

        # 3. Giả lập client bị ngắt mạng / ngắt kết nối giữa chừng (Tạm dừng poll).
        # Cho phép event loop tự động thực thi background task của Backend
        await asyncio.sleep(0.1)

        # 4. Client mở lại app / khôi phục kết nối và poll đến khi nhận kết quả hoàn tất
        repoll_data = await poll_until_terminal(ac, chat_req_id, headers)
        assert repoll_data["state"] == "COMPLETED"
        assert repoll_data["answer"] is not None
        assert repoll_data["citations"] is not None

        # Kiểm tra các thuộc tính is_official_policy và source_type trong citations
        for cit in repoll_data["citations"]:
            assert "is_official_policy" in cit
            assert "source_type" in cit


@pytest.mark.asyncio
async def test_e2e_client_reload_fetches_persisted_conversation_history():
    """Mô phỏng trường hợp client bị crash / reload trang web hoàn toàn,

    client khôi phục lại lịch sử cuộc hội thoại qua GET /conversations/{id}/messages.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = get_e2e_auth_header()
        conv_id = "66666666-6666-6666-6666-666666666666"

        # Client gọi API lấy danh sách tin nhắn sau khi reload
        msg_res = await ac.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
        assert msg_res.status_code == 200
        msg_data = msg_res.json()
        assert msg_data["success"] is True
        messages = msg_data["data"]["messages"]
        assert len(messages) >= 2

        # Đảm bảo tin nhắn assistant được lưu trữ đầy đủ thuộc tính citation
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) > 0
        latest_assistant_msg = assistant_msgs[-1]

        if latest_assistant_msg.get("citations"):
            for cit in latest_assistant_msg["citations"]:
                assert "is_official_policy" in cit
                assert "source_type" in cit


@pytest.mark.asyncio
async def test_e2e_retry_flow_after_interrupted_failure():
    """Mô phỏng trường hợp yêu cầu bị từ chối, Backend tự động chạy background task và client gọi /retry."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = get_e2e_auth_header()
        conv_id = "66666666-6666-6666-6666-666666666666"
        question = "Câu hỏi này không có trong tài liệu"

        submit_resp = await ac.post(
            "/api/v1/chat/requests",
            json={"conversation_id": conv_id, "question": question},
            headers=headers,
        )
        chat_req_id = submit_resp.json()["data"]["chat_request_id"]

        # Đợi backend tự động hoàn thành background task cho request 1
        parent_result = await poll_until_terminal(ac, chat_req_id, headers)
        assert parent_result["state"] == "REFUSED"

        # Client gửi lệnh retry (Backend tiếp tục tự động sinh background task mới)
        retry_resp = await ac.post(
            f"/api/v1/chat/requests/{chat_req_id}/retry",
            json={"reason": "USER_RETRY"},
            headers=headers,
        )
        assert retry_resp.status_code == 202
        retry_data = retry_resp.json()
        assert retry_data["success"] is True
        new_chat_req_id = retry_data["data"]["chat_request_id"]

        # Client poll request mới đến khi hoàn thành tự động
        final_result = await poll_until_terminal(ac, new_chat_req_id, headers)
        assert final_result["state"] in ("COMPLETED", "REFUSED")


@pytest.mark.asyncio
async def test_e2e_concurrent_load_10_to_30_requests():
    """Kiểm thử tải đồng thời từ 10 đến 30 luồng chat hoạt động song song.

    Đo lường thời gian hoàn tất, độ trễ P95, tỷ lệ thành công và kiểm tra tính nhất quán dữ liệu.
    """
    headers = get_e2e_auth_header()

    for concurrency in (10, 20, 30):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            start_time = time.monotonic()

            async def run_single_user_chat(index: int) -> dict:
                # Tránh va chạm thời điểm gọi DB commit chính xác cùng microsecond
                await asyncio.sleep(index * 0.005)
                user_start = time.monotonic()

                # 1. Tạo phiên hội thoại riêng
                conv_resp = await ac.post(
                    "/api/v1/conversations",
                    json={"title": f"Concurrent Conv {concurrency}-{index}"},
                    headers=headers,
                )
                assert conv_resp.status_code == 201
                conv_id = conv_resp.json()["data"]["conversation_id"]

                # 2. Gửi câu hỏi chat
                question = f"Quy định nghỉ phép năm và thử việc của nhân viên luồng {index}?"
                submit_resp = await ac.post(
                    "/api/v1/chat/requests",
                    json={"conversation_id": conv_id, "question": question},
                    headers=headers,
                )
                assert submit_resp.status_code == 202
                chat_req_id = submit_resp.json()["data"]["chat_request_id"]

                # 3. Poll cho tới khi hoàn tất
                res = await poll_until_terminal(ac, chat_req_id, headers, timeout_seconds=20.0)
                latency = int((time.monotonic() - user_start) * 1000)

                # Kiểm tra tính toàn vẹn thuộc tính
                assert res["state"] in ("COMPLETED", "REFUSED")
                if res.get("citations"):
                    for cit in res["citations"]:
                        assert "is_official_policy" in cit
                        assert "source_type" in cit
                return {"latency_ms": latency, "state": res["state"]}

            tasks = [run_single_user_chat(i) for i in range(concurrency)]
            results = await asyncio.gather(*tasks)

            total_elapsed = time.monotonic() - start_time
            latencies = [r["latency_ms"] for r in results]
            latencies.sort()
            avg_latency = sum(latencies) / len(latencies)
            p95_index = int(len(latencies) * 0.95)
            p95_latency = latencies[min(p95_index, len(latencies) - 1)]
            success_count = sum(1 for r in results if r["state"] in ("COMPLETED", "REFUSED"))

            assert success_count == concurrency


@pytest.mark.asyncio
async def test_e2e_idempotency_and_duplicate_retry_limits():
    """Kiểm thử tính idempotency và kiểm soát thử lại trùng lặp (Duplicate Retry Limits).

    Xác minh:
    1. Không cho phép retry đối với request đã COMPLETED thành công (HTTP 409 REQUEST_NOT_RETRYABLE).
    2. Cho phép retry tối đa 3 lần cho request bị từ chối/lỗi.
    3. Trả về HTTP 409 RETRY_LIMIT_REACHED khi vượt quá giới hạn 3 lần thử lại trùng lặp.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = get_e2e_auth_header()

        # Tạo phiên hội thoại test idempotency
        conv_resp = await ac.post(
            "/api/v1/conversations",
            json={"title": "Idempotency Test Conv"},
            headers=headers,
        )
        conv_id = conv_resp.json()["data"]["conversation_id"]

        # Kịch bản 1: Request COMPLETED không thể retry trùng lặp
        completed_submit = await ac.post(
            "/api/v1/chat/requests",
            json={"conversation_id": conv_id, "question": "Thời gian thử việc?"},
            headers=headers,
        )
        completed_req_id = completed_submit.json()["data"]["chat_request_id"]
        comp_res = await poll_until_terminal(ac, completed_req_id, headers)
        assert comp_res["state"] == "COMPLETED"

        duplicate_retry_resp = await ac.post(
            f"/api/v1/chat/requests/{completed_req_id}/retry",
            json={"reason": "DUPLICATE_RETRY"},
            headers=headers,
        )
        assert duplicate_retry_resp.status_code == 409
        assert duplicate_retry_resp.json()["error"]["code"] == "REQUEST_NOT_RETRYABLE"

        # Kịch bản 2: Request REFUSED cho phép retry tối đa 3 lần
        refused_submit = await ac.post(
            "/api/v1/chat/requests",
            json={"conversation_id": conv_id, "question": "Không có trong tài liệu"},
            headers=headers,
        )
        curr_req_id = refused_submit.json()["data"]["chat_request_id"]
        await poll_until_terminal(ac, curr_req_id, headers)

        # Retry 1
        r1 = await ac.post(
            f"/api/v1/chat/requests/{curr_req_id}/retry",
            headers={"Idempotency-Key": str(uuid.uuid4()), **headers},
        )
        assert r1.status_code == 202
        curr_req_id = r1.json()["data"]["chat_request_id"]
        await poll_until_terminal(ac, curr_req_id, headers)

        # Retry 2
        r2 = await ac.post(
            f"/api/v1/chat/requests/{curr_req_id}/retry",
            headers={"Idempotency-Key": str(uuid.uuid4()), **headers},
        )
        assert r2.status_code == 202
        curr_req_id = r2.json()["data"]["chat_request_id"]
        await poll_until_terminal(ac, curr_req_id, headers)

        # Retry 3
        r3 = await ac.post(
            f"/api/v1/chat/requests/{curr_req_id}/retry",
            headers={"Idempotency-Key": str(uuid.uuid4()), **headers},
        )
        assert r3.status_code == 202
        curr_req_id = r3.json()["data"]["chat_request_id"]
        await poll_until_terminal(ac, curr_req_id, headers)

        # Retry 4 (Vượt giới hạn 3 lần retry trùng lặp)
        r4 = await ac.post(
            f"/api/v1/chat/requests/{curr_req_id}/retry",
            headers={"Idempotency-Key": str(uuid.uuid4()), **headers},
        )
        assert r4.status_code == 409
        assert r4.json()["error"]["code"] == "RETRY_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_e2e_true_idempotency_same_key_prevents_duplicate_messages_and_tickets():
    """Kiểm thử trường hợp Idempotency thật sự với cùng Idempotency-Key.

    Xác minh:
    1. Khi client gửi duplicate submit/retry với cùng Idempotency-Key hoặc thực thi đồng thời worker,
    2. CSDL kiểm soát khóa row/lock, đảm bảo KHÔNG TẠO duplicate messages (chỉ 1 user msg, 1 assistant msg)
    3. Đảm bảo KHÔNG TẠO duplicate tickets khi câu hỏi thuộc luồng escalate.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = get_e2e_auth_header()
        idempotency_key = f"idem-key-{uuid.uuid4()}"

        # 1. Tạo phiên hội thoại
        conv_resp = await ac.post(
            "/api/v1/conversations",
            json={"title": "Same Idempotency Key Conv"},
            headers={"Idempotency-Key": idempotency_key, **headers},
        )
        assert conv_resp.status_code == 201
        conv_id = conv_resp.json()["data"]["conversation_id"]

        # 2. Gửi câu hỏi RAG gây escalate (tạo ticket) kèm Idempotency-Key
        question = "Câu hỏi này không có trong tài liệu"
        submit_resp = await ac.post(
            "/api/v1/chat/requests",
            json={"conversation_id": conv_id, "question": question},
            headers={"Idempotency-Key": idempotency_key, **headers},
        )
        assert submit_resp.status_code == 202
        chat_req_id = submit_resp.json()["data"]["chat_request_id"]
        chat_req_uuid = uuid.UUID(chat_req_id)

        # 3. Giả lập 2 worker bất đồng bộ chạy trùng lặp cùng 1 request_id đồng thời
        w1 = ChatService._process_chat_rag_request(
            chat_request_id=chat_req_uuid,
            user_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            department="Engineering",
            question=question,
            conversation_id=uuid.UUID(conv_id),
        )
        w2 = ChatService._process_chat_rag_request(
            chat_request_id=chat_req_uuid,
            user_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            department="Engineering",
            question=question,
            conversation_id=uuid.UUID(conv_id),
        )
        await asyncio.gather(w1, w2)

        # 4. Polling lấy kết quả hoàn tất
        res = await poll_until_terminal(ac, chat_req_id, headers)
        assert res["state"] == "REFUSED"

        # 5. Kiểm tra CSDL đảm bảo KHÔNG trùng lặp Messages và Tickets
        async with TestingSessionLocal() as session:
            # Kiểm tra số lượng tin nhắn trong phiên
            msg_res = await session.execute(
                select(func.count(MessageDB.id)).where(MessageDB.conversation_id == uuid.UUID(conv_id))
            )
            msg_count = msg_res.scalar()
            # 1 tin user + 1 tin assistant duy nhất = 2
            assert msg_count == 2

            # Kiểm tra tin nhắn assistant chỉ có 1
            asst_msg_res = await session.execute(
                select(MessageDB).where(
                    MessageDB.conversation_id == uuid.UUID(conv_id),
                    MessageDB.role == "assistant",
                )
            )
            asst_msgs = list(asst_msg_res.scalars().all())
            assert len(asst_msgs) == 1
            latest_asst_msg = asst_msgs[0]

            # Kiểm tra số lượng Ticket tạo ra cho tin nhắn này chỉ duy nhất 1 ticket
            tck_res = await session.execute(
                select(func.count(TicketDB.id)).where(TicketDB.message_id == latest_asst_msg.id)
            )
            ticket_count = tck_res.scalar()
            assert ticket_count == 1


@pytest.mark.asyncio
async def test_e2e_fastapi_server_restart_crash_background_job_recovery():
    """Mô phỏng trường hợp FastAPI server bị crash / restart đột ngột giữa chừng.

    Xác minh:
    1. Request đã commit vào CSDL dạng QUEUED không bị mất dữ liệu khi server sập.
    2. Sau khi server restart, background job recovery tiếp tục được xử lý tới COMPLETED.
    3. Client re-poll thành công mà không phải gửi lại câu hỏi mới.
    """
    headers = get_e2e_auth_header()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        conv_resp = await ac.post(
            "/api/v1/conversations",
            json={"title": "Crash Recovery Conv"},
            headers=headers,
        )
        conv_id = conv_resp.json()["data"]["conversation_id"]

        # Step 1: Tạm tắt background task để mô phỏng server bị crash ngay khi vừa vung request vào DB QUEUED
        ChatService.background_tasks_enabled = False

        submit_resp = await ac.post(
            "/api/v1/chat/requests",
            json={"conversation_id": conv_id, "question": "Quy định làm việc xa nhà?"},
            headers=headers,
        )
        assert submit_resp.status_code == 202
        chat_req_id = submit_resp.json()["data"]["chat_request_id"]
        chat_req_uuid = uuid.UUID(chat_req_id)

        # Kiểm tra dữ liệu đã lưu dạng QUEUED trong DB
        poll_queued = await ac.get(f"/api/v1/chat/requests/{chat_req_id}", headers=headers)
        assert poll_queued.json()["data"]["state"] == "QUEUED"

        # Step 2: Giả lập Server FastAPI Khởi động lại (Restart / Crash Recovery)
        # Bật lại background processing & khôi phục worker xử lý các job QUEUED còn tồn đọng trong DB
        ChatService.background_tasks_enabled = True

        async with TestingSessionLocal() as session:
            pending_res = await session.execute(
                select(ChatRequestDB).where(
                    ChatRequestDB.id == chat_req_uuid,
                    ChatRequestDB.state == "QUEUED",
                )
            )
            pending_job = pending_res.scalar_one_or_none()
            assert pending_job is not None

        # Background recovery worker tiếp tục xử lý job bị dở dang sau khi restart
        await ChatService._process_chat_rag_request(
            chat_request_id=chat_req_uuid,
            user_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            department="Engineering",
            question="Quy định làm việc xa nhà?",
            conversation_id=uuid.UUID(conv_id),
        )

        # Step 3: Client re-poll và nhận kết quả COMPLETED hoàn chỉnh
        final_res = await poll_until_terminal(ac, chat_req_id, headers)
        assert final_res["state"] == "COMPLETED"
        assert final_res["answer"] is not None
        assert final_res["citations"] is not None



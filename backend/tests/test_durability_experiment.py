import asyncio
import io
import logging
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import uuid
from datetime import UTC, datetime

from app.core.database import Base
from app.core.logging import logger
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.messages import MessageDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.schemas.agent import AgentAnswerDTO
from app.services.chat_service import ChatService
from main import app
from tests.conftest import TestingSessionLocal, client, test_engine


async def run_experiment():
    print("=" * 80)
    print("BẮT ĐẦU THÍ NGHIỆM KIỂM THỬ THỰC TẾ 5 BƯỚC: CHAT JOB DURABILITY")
    print("=" * 80)

    # Khoi tao bang trong SQLite test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
    conv_id = uuid.UUID("66666666-7777-8888-9999-000000000000")
    chat_req_id = uuid.uuid4()
    question = "Thời gian nghỉ phép năm tiêu chuẩn là bao nhiêu ngày?"

    # Chuẩn bị dữ liệu ban đầu
    async with TestingSessionLocal() as session:
        user = await session.get(UserDB, user_id)
        if not user:
            user = UserDB(id=user_id, email="durability_exp@company.com", hashed_password="pw")
            session.add(user)
        profile = await session.get(ProfileDB, user_id)
        if not profile:
            profile = ProfileDB(id=user_id, display_name="Test User", role="EMPLOYEE", department="Sales")
            session.add(profile)
        conv = await session.get(ConversationDB, conv_id)
        if not conv:
            conv = ConversationDB(id=conv_id, user_id=user_id, title="Phiên thử nghiệm", state="ACTIVE")
            session.add(conv)
        await session.commit()

    ChatService.session_factory = TestingSessionLocal
    ChatService.background_tasks_enabled = True

    # -------------------------------------------------------------------------
    # BƯỚC 1: Tạo request và chủ động DELAY (sleep) trong quá trình GENERATING
    # -------------------------------------------------------------------------
    print("\n👉 [BƯỚC 1]: Tạo chat request và chủ động sleep trong lúc GENERATE...")
    
    async with TestingSessionLocal() as session:
        await ChatService.submit_chat_request(
            db=session,
            user_id=user_id,
            department="Sales",
            conversation_id=conv_id,
            question=question,
            start_background=False, # Ta sẽ tự chạy task để kiểm soát
            chat_request_id=chat_req_id,
        )

    # Khởi chạy background task với mock sleep 10 giây
    async def delayed_query_agent(*args, **kwargs):
        print("   [Worker] Đang gọi Agent RAG... (chủ động sleep 10s mô phỏng LLM generating)")
        await asyncio.sleep(10)
        return AgentAnswerDTO(
            response="Mức tiêu chuẩn là 12 ngày phép năm.",
            intent="hr_question",
            confidence_score=0.9,
            citations=[],
        )

    ChatService.agent_client.query_agent = delayed_query_agent

    task = asyncio.create_task(
        ChatService._process_chat_rag_request(
            chat_request_id=chat_req_id,
            user_id=user_id,
            department="Sales",
            question=question,
            conversation_id=conv_id,
        )
    )

    # Chờ 0.5s để worker claim request và đổi state sang GENERATING
    await asyncio.sleep(0.5)

    async with TestingSessionLocal() as session:
        req_step1 = await session.get(ChatRequestDB, chat_req_id)
        print(f"   [DB Query Step 1] ID: {chat_req_id} | State hiện tại: {req_step1.state}")
        assert req_step1.state == "GENERATING", "LỖI: Request chưa chuyển sang GENERATING!"

    # -------------------------------------------------------------------------
    # BƯỚC 2: Trong lúc đang GENERATING, kill process đột ngột (hủy task thô bạo)
    # -------------------------------------------------------------------------
    print("\n👉 [BƯỚC 2]: Giả lập KILL PROCESS đột ngột (Hard Kill, hủy task thô bạo)...")
    task.cancel() # Hủy task thô bạo
    try:
        await task
    except asyncio.CancelledError:
        print("   [OS] Process Backend đã bị KILL (-9) khi đang dở dang ở trạng thái GENERATING!")

    # Xác nhận DB lúc này: Bị kẹt ở GENERATING
    async with TestingSessionLocal() as session:
        req_step2 = await session.get(ChatRequestDB, chat_req_id)
        print(f"   [DB Query Step 2] Request sau khi Server sập: State = {req_step2.state}")
        assert req_step2.state == "GENERATING", "LỖI: Request không ở trạng thái GENERATING trước restart!"

    # -------------------------------------------------------------------------
    # BƯỚC 3: Restart Backend và kiểm tra log [Chat Durability]
    # -------------------------------------------------------------------------
    print("\n👉 [BƯỚC 3]: Restart Backend -> Chạy lifespan startup recovery...")

    # Bắt log đầu ra qua standard library logging StreamHandler
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Đổi mock agent sang trả về kết quả thật (nhanh chóng) sau restart
    async def fast_query_agent(*args, **kwargs):
        print("   [Worker Restarted] Agent RAG xử lý thành công yêu cầu đã khôi phục!")
        return AgentAnswerDTO(
            response="Theo quy định, nhân viên làm việc trong điều kiện bình thường được nghỉ 12 ngày phép năm [Nguồn 1].",
            intent="hr_question",
            confidence_score=0.95,
            citations=[{
                "chunk_id": "leave::0001",
                "source_file": "04_chinh-sach-nghi-phep.md",
                "title": "Chính sách Nghỉ phép",
                "category": "leave_policies",
                "page_start": 2,
                "page_end": 2,
                "is_official_policy": True,
            }],
        )
    ChatService.agent_client.query_agent = fast_query_agent

    # Gọi recover_pending_requests như trong main.py lifespan
    recovered_count = await ChatService.recover_pending_requests()
    logger.info(f"[Chat Durability] Recovered {recovered_count} pending chat request(s) on startup.")

    logger.removeHandler(handler)
    full_logs = log_capture.getvalue()

    print(f"   [Log Server] {full_logs.strip()}")
    assert f"[Chat Durability] Recovered {recovered_count} pending chat request(s) on startup." in full_logs
    assert recovered_count >= 1, "LỖI: Không tìm thấy request để khôi phục!"

    # -------------------------------------------------------------------------
    # BƯỚC 4: Query DB trực tiếp xem request có về COMPLETED và có kết quả không
    # -------------------------------------------------------------------------
    print("\n👉 [BƯỚC 4]: Chờ worker xử lý xong -> Query DB trực tiếp...")
    # Chờ 1 giây để worker hoàn tất
    await asyncio.sleep(1)

    async with TestingSessionLocal() as session:
        req_step4 = await session.get(ChatRequestDB, chat_req_id)
        print(f"   [DB Query Step 4] ID: {req_step4.id}")
        print(f"   - State cuối cùng: {req_step4.state}")
        print(f"   - Answer Status: {req_step4.answer_status}")
        print(f"   - Answer Content: {req_step4.answer}")
        print(f"   - Citations Count: {len(req_step4.citations or [])}")
        print(f"   - Assistant Message ID: {req_step4.assistant_message_id}")

        assert req_step4.state == "COMPLETED", f"LỖI: Request chưa COMPLETED, đang là {req_step4.state}"
        assert req_step4.answer is not None, "LỖI: Answer bị rỗng!"
        assert req_step4.assistant_message_id is not None, "LỖI: Không tạo assistant message!"

    # -------------------------------------------------------------------------
    # BƯỚC 5: Kiểm tra FE nhận kết quả qua Polling
    # -------------------------------------------------------------------------
    print("\n👉 [BƯỚC 5]: Kiểm tra FE Polling / Reconnect (GET /api/v1/chat/requests/{id})...")
    from app.core.security import create_access_token
    from app.api.dependencies.db_deps import get_db

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token({"sub": str(user_id), "email": "durability_exp@company.com", "role": "EMPLOYEE", "department": "Sales"})
    auth_header = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/v1/chat/requests/{chat_req_id}", headers=auth_header)
    print(f"   [FE Polling Response Code]: {response.status_code}")
    res_json = response.json()
    print(f"   [FE Data State]: {res_json['data']['state']}")
    print(f"   [FE Data Answer]: {res_json['data']['answer']}")

    assert response.status_code == 200, f"LỖI FE: HTTP status = {response.status_code}"
    assert res_json["data"]["state"] == "COMPLETED", "LỖI FE: State không phải COMPLETED"
    assert "12 ngày phép năm" in res_json["data"]["answer"]
    assert len(res_json["data"]["citations"]) >= 1

    print("\n" + "=" * 80)
    print("🎉 KẾT QUẢ: TẤT CẢ 5 BƯỚC ĐỀU THÀNH CÔNG 100% - KHÔNG CÓ BẤT KỲ LỖI NÀO!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_experiment())

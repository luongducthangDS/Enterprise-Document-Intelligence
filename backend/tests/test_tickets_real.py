import uuid
from datetime import UTC, datetime
import pytest
import pytest_asyncio

from app.core.security import create_access_token, hash_password
from app.domain.models.profile import ProfileDB
from app.domain.models.ticket import TicketDB
from app.domain.models.user import UserDB
from app.schemas.agent import AgentTicketDraftDTO
from app.schemas.ticket import TicketCreateRequest, TicketUpdateRequest
from app.services.ticket_service import TicketService
from tests.conftest import TestingSessionLocal, client


async def ensure_user_and_profile(session, user_id, email, display_name, role, department):
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
            role=role,
            department=department,
        )
        session.add(profile)
        await session.flush()


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_real_tickets_test_data():
    async with TestingSessionLocal() as session:
        emp1_id = uuid.UUID("11111111-aaaa-1111-aaaa-111111111111")
        emp2_id = uuid.UUID("22222222-bbbb-2222-bbbb-222222222222")
        admin_id = uuid.UUID("99999999-cccc-9999-cccc-999999999999")

        acc_mgr_id = uuid.UUID("33333333-cccc-3333-cccc-333333333333")
        prod_mgr_id = uuid.UUID("44444444-cccc-4444-cccc-444444444444")

        await ensure_user_and_profile(session, emp1_id, "emp1_real@company.com", "Employee One", "EMPLOYEE", "Sales")
        await ensure_user_and_profile(session, emp2_id, "emp2_real@company.com", "Employee Two", "EMPLOYEE", "Engineering")
        await ensure_user_and_profile(session, admin_id, "admin_real@company.com", "HR Admin Real", "DEPARTMENT_MANAGER", "HR")
        await ensure_user_and_profile(session, acc_mgr_id, "acc_mgr@company.com", "Accounting Manager", "DEPARTMENT_MANAGER", "Accounting")
        await ensure_user_and_profile(session, prod_mgr_id, "prod_mgr@company.com", "Product Manager", "DEPARTMENT_MANAGER", "Product")

        await session.commit()


def get_token_header(user_id: str, email: str, role: str, department: str) -> dict:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "department": department,
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


class TestTicketAPIReal:
    """Tác nhân 3 & 4: Kiểm thử toàn diện Ticket API Thật & Thẩm định QA Edge Cases."""

    def test_create_ticket_manual_employee(self):
        """Tạo ticket thủ công bởi nhân viên."""
        headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")
        payload = {
            "employee_question": "Tôi muốn hỏi về thủ tục đăng ký phụ thuộc giảm trừ gia cảnh thuế TNCN",
            "category": "tax_policies",
            "target_department": "CB",
            "priority": "High",
            "escalate_reason": "personal_data_required",
        }
        resp = client.post("/api/v1/tickets", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["ticket_code"].startswith("TCK-")
        assert data["employee_question"] == payload["employee_question"]
        assert data["target_department"] == "CB"
        assert data["priority"] == "High"
        assert data["status"] == "open"
        assert data["requester_name"] == "Employee One"

    def test_create_ticket_fallback_values(self):
        """Tác nhân 4 QA Edge Case: Fallback department và priority khi client gửi sai format."""
        headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")
        payload = {
            "employee_question": "Câu hỏi test fallback",
            "target_department": "UNKNOWN_DEPT",  # Phải fallback về HRBP
            "priority": "EXTREME",                # Phải fallback về Medium
            "escalate_reason": "invalid_reason",   # Phải fallback về user_requested_human
        }
        resp = client.post("/api/v1/tickets", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["target_department"] == "HRBP"
        assert data["priority"] == "Medium"
        assert data["escalate_reason"] == "user_requested_human"

    @pytest.mark.asyncio
    async def test_create_ticket_from_agent_draft_persistence(self):
        """Tạo ticket từ Agent Escalation Draft qua Service."""
        from app.domain.models.conversations import ConversationDB
        from app.domain.models.messages import MessageDB

        async with TestingSessionLocal() as session:
            requester_id = uuid.UUID("11111111-aaaa-1111-aaaa-111111111111")
            conv_id = uuid.uuid4()
            msg_id = uuid.uuid4()

            conv = ConversationDB(
                id=conv_id,
                user_id=requester_id,
                title="Hội thoại thắc mắc lương",
                state="ACTIVE",
            )
            session.add(conv)
            await session.flush()

            msg = MessageDB(
                id=msg_id,
                conversation_id=conv_id,
                role="USER",
                content="Lương tháng trước của em tại sao bị trừ 500k?",
            )
            session.add(msg)
            await session.flush()

            draft = AgentTicketDraftDTO(
                employee_question="Lương tháng trước của em tại sao bị trừ 500k?",
                escalate_reason="personal_data_required",
                confidence_score=0.1,
                category="compensation_policies",
                target_department="CB",
                priority="Medium",
            )

            ticket_db = await TicketService.create_from_agent_draft(
                db=session,
                draft=draft,
                conversation_id=conv_id,
                message_id=msg_id,
                requester_id=requester_id,
            )
            await session.commit()

            assert ticket_db.id is not None
            assert ticket_db.ticket_code.startswith("TCK-")
            assert ticket_db.conversation_id == conv_id
            assert ticket_db.message_id == msg_id
            assert ticket_db.status == "open"
            assert ticket_db.target_department == "CB"

    def test_list_tickets_rbac_employee_isolation(self):
        """Employee 1 chỉ thấy ticket của mình, Employee 2 không thấy ticket của Employee 1."""
        emp1_headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")
        emp2_headers = get_token_header("22222222-bbbb-2222-bbbb-222222222222", "emp2_real@company.com", "EMPLOYEE", "Engineering")

        # Employee 1 tạo 1 ticket
        client.post(
            "/api/v1/tickets",
            json={"employee_question": "Private Question of Emp 1"},
            headers=emp1_headers,
        )

        # Employee 1 list -> thấy
        resp1 = client.get("/api/v1/tickets", headers=emp1_headers)
        assert resp1.status_code == 200
        tickets1 = resp1.json()["data"]
        assert any(t["employee_question"] == "Private Question of Emp 1" for t in tickets1)

        # Employee 2 list -> KHÔNG thấy
        resp2 = client.get("/api/v1/tickets", headers=emp2_headers)
        assert resp2.status_code == 200
        tickets2 = resp2.json()["data"]
        assert not any(t["employee_question"] == "Private Question of Emp 1" for t in tickets2)

    def test_admin_list_and_filter_tickets(self):
        """HR Admin xem được tất cả tickets và lọc theo phòng ban / trạng thái."""
        admin_headers = get_token_header("99999999-cccc-9999-cccc-999999999999", "admin_real@company.com", "DEPARTMENT_MANAGER", "HR")
        emp1_headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")

        # Tạo ticket thuộc phòng ban TA
        client.post(
            "/api/v1/tickets",
            json={"employee_question": "Hỏi về tuyển dụng referral", "target_department": "TA"},
            headers=emp1_headers,
        )

        # Admin filter department TA
        resp = client.get("/api/v1/tickets?department=TA", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert all(t["target_department"] == "TA" for t in data)

    def test_ticket_detail_access_forbidden(self):
        """Employee 2 không được xem chi tiết ticket của Employee 1."""
        emp1_headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")
        emp2_headers = get_token_header("22222222-bbbb-2222-bbbb-222222222222", "emp2_real@company.com", "EMPLOYEE", "Engineering")

        create_resp = client.post(
            "/api/v1/tickets",
            json={"employee_question": "Bảo mật cá nhân"},
            headers=emp1_headers,
        )
        ticket_id = create_resp.json()["data"]["id"]

        # Employee 2 xem -> 403 Forbidden
        view_resp = client.get(f"/api/v1/tickets/{ticket_id}", headers=emp2_headers)
        assert view_resp.status_code == 403
        assert view_resp.json()["error"]["code"] == "TICKET_ACCESS_DENIED"

    def test_ticket_lifecycle_transitions(self):
        """Vòng đời hoàn chỉnh: OPEN -> IN_PROGRESS -> RESOLVED -> CLOSED."""
        emp1_headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")
        admin_headers = get_token_header("99999999-cccc-9999-cccc-999999999999", "admin_real@company.com", "DEPARTMENT_MANAGER", "HR")

        # 1. Tạo ticket
        create_resp = client.post(
            "/api/v1/tickets",
            json={"employee_question": "Hỏi về bảo hiểm thai sản"},
            headers=emp1_headers,
        )
        ticket_id = create_resp.json()["data"]["id"]
        assert create_resp.json()["data"]["status"] == "open"

        # 2. Admin tiếp nhận -> IN_PROGRESS
        patch1 = client.patch(
            f"/api/v1/tickets/{ticket_id}",
            json={"status": "in_progress"},
            headers=admin_headers,
        )
        assert patch1.status_code == 200
        assert patch1.json()["data"]["status"] == "in_progress"
        assert patch1.json()["data"]["assignee_id"] is not None

        # 3. Admin cố hoàn thành nhưng thiếu resolution_note -> Conflict 409
        patch2_fail = client.patch(
            f"/api/v1/tickets/{ticket_id}",
            json={"status": "resolved"},
            headers=admin_headers,
        )
        assert patch2_fail.status_code == 409
        assert patch2_fail.json()["error"]["code"] == "RESOLUTION_NOTE_REQUIRED"

        # 4. Admin hoàn thành kèm resolution_note -> RESOLVED
        patch2_ok = client.patch(
            f"/api/v1/tickets/{ticket_id}",
            json={"status": "resolved", "resolution_note": "Đã hướng dẫn nộp hồ sơ giấy ốm qua HR Portal"},
            headers=admin_headers,
        )
        assert patch2_ok.status_code == 200
        assert patch2_ok.json()["data"]["status"] == "resolved"
        assert patch2_ok.json()["data"]["resolved_at"] is not None

        # 5. Employee xác nhận đóng ticket -> CLOSED
        close_resp = client.patch(
            f"/api/v1/tickets/{ticket_id}",
            json={"status": "closed"},
            headers=emp1_headers,
        )
        assert close_resp.status_code == 200
        assert close_resp.json()["data"]["status"] == "closed"
        assert close_resp.json()["data"]["closed_at"] is not None

    def test_create_ticket_accounting_and_product_departments(self):
        """Kiểm tra tạo ticket gửi tới các phòng ban Accounting, Product, HR chuẩn hóa đúng canonical."""
        emp_headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")

        # 1. Tạo ticket phòng Accounting (FE gửi "Accounting")
        resp_acc = client.post(
            "/api/v1/tickets",
            json={
                "employee_question": "Tôi muốn hỏi về thủ tục xuất hóa đơn VAT và hoàn ứng công tác",
                "category": "accounting_invoicing",
                "target_department": "Accounting",
                "priority": "High",
            },
            headers=emp_headers,
        )
        assert resp_acc.status_code == 201
        data_acc = resp_acc.json()["data"]
        assert data_acc["target_department"] == "ACCOUNTING"
        assert data_acc["employee_question"].startswith("Tôi muốn hỏi về thủ tục xuất hóa đơn")

        # 2. Tạo ticket phòng Product (FE gửi "Product")
        resp_prod = client.post(
            "/api/v1/tickets",
            json={
                "employee_question": "Đề xuất tính năng tích hợp AI search cho khách hàng",
                "category": "product_feature",
                "target_department": "Product",
                "priority": "Medium",
            },
            headers=emp_headers,
        )
        assert resp_prod.status_code == 201
        data_prod = resp_prod.json()["data"]
        assert data_prod["target_department"] == "PRODUCT"

        # 3. Tạo ticket phòng HR (FE gửi "HR")
        resp_hr = client.post(
            "/api/v1/tickets",
            json={
                "employee_question": "Hỏi về nội quy làm việc hybrid toàn công ty",
                "category": "general_hr",
                "target_department": "HR",
                "priority": "Low",
            },
            headers=emp_headers,
        )
        assert resp_hr.status_code == 201
        data_hr = resp_hr.json()["data"]
        assert data_hr["target_department"] == "HR"

    def test_department_manager_scoped_tickets(self):
        """Kiểm tra phân quyền Department Manager chỉ xem và quản lý đúng ticket phòng ban mình."""
        emp_headers = get_token_header("11111111-aaaa-1111-aaaa-111111111111", "emp1_real@company.com", "EMPLOYEE", "Sales")
        acc_mgr_headers = get_token_header("33333333-cccc-3333-cccc-333333333333", "acc_mgr@company.com", "DEPARTMENT_MANAGER", "Accounting")
        prod_mgr_headers = get_token_header("44444444-cccc-4444-cccc-444444444444", "prod_mgr@company.com", "DEPARTMENT_MANAGER", "Product")
        hr_mgr_headers = get_token_header("99999999-cccc-9999-cccc-999999999999", "admin_real@company.com", "DEPARTMENT_MANAGER", "HR")

        # Tạo ticket Accounting
        res1 = client.post(
            "/api/v1/tickets",
            json={"employee_question": "Yêu cầu quyết toán chi phí tháng 8", "target_department": "Accounting"},
            headers=emp_headers,
        )
        acc_ticket_id = res1.json()["data"]["id"]

        # Tạo ticket Product
        res2 = client.post(
            "/api/v1/tickets",
            json={"employee_question": "Yêu cầu chỉnh sửa luồng checkout", "target_department": "Product"},
            headers=emp_headers,
        )
        prod_ticket_id = res2.json()["data"]["id"]

        # 1. Accounting Manager chỉ thấy ticket Accounting
        acc_list = client.get("/api/v1/tickets", headers=acc_mgr_headers)
        assert acc_list.status_code == 200
        acc_tickets = acc_list.json()["data"]
        acc_ids = [t["id"] for t in acc_tickets]
        assert acc_ticket_id in acc_ids
        assert prod_ticket_id not in acc_ids
        assert all(t["target_department"] == "ACCOUNTING" for t in acc_tickets)

        # 2. Product Manager chỉ thấy ticket Product
        prod_list = client.get("/api/v1/tickets", headers=prod_mgr_headers)
        assert prod_list.status_code == 200
        prod_tickets = prod_list.json()["data"]
        prod_ids = [t["id"] for t in prod_tickets]
        assert prod_ticket_id in prod_ids
        assert acc_ticket_id not in prod_ids
        assert all(t["target_department"] == "PRODUCT" for t in prod_tickets)

        # 3. HR Manager không thấy ticket của Accounting hay Product
        hr_list = client.get("/api/v1/tickets", headers=hr_mgr_headers)
        assert hr_list.status_code == 200
        hr_ids = [t["id"] for t in hr_list.json()["data"]]
        assert acc_ticket_id not in hr_ids
        assert prod_ticket_id not in hr_ids

        # 4. Accounting Manager xem chi tiết ticket Accounting thành công
        acc_detail = client.get(f"/api/v1/tickets/{acc_ticket_id}", headers=acc_mgr_headers)
        assert acc_detail.status_code == 200
        assert acc_detail.json()["data"]["target_department"] == "ACCOUNTING"

        # 5. Accounting Manager cố tình xem ticket Product -> 403 Forbidden
        forbidden_detail = client.get(f"/api/v1/tickets/{prod_ticket_id}", headers=acc_mgr_headers)
        assert forbidden_detail.status_code == 403
        assert forbidden_detail.json()["error"]["code"] == "TICKET_ACCESS_DENIED"

        # 6. Accounting Manager cập nhật tiếp nhận ticket Accounting -> 200 OK
        patch_acc = client.patch(
            f"/api/v1/tickets/{acc_ticket_id}",
            json={"status": "in_progress"},
            headers=acc_mgr_headers,
        )
        assert patch_acc.status_code == 200
        assert patch_acc.json()["data"]["status"] == "in_progress"
        assert patch_acc.json()["data"]["assignee_id"] == "33333333-cccc-3333-cccc-333333333333"

        # 7. Accounting Manager cố cập nhật ticket Product -> 403 Forbidden
        patch_forbidden = client.patch(
            f"/api/v1/tickets/{prod_ticket_id}",
            json={"status": "in_progress"},
            headers=acc_mgr_headers,
        )
        assert patch_forbidden.status_code == 403
        assert patch_forbidden.json()["error"]["code"] == "FORBIDDEN"

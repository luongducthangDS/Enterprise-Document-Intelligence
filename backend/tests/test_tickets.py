import uuid

import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB

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
async def setup_tickets_test_data():
    async with TestingSessionLocal() as session:
        user_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        admin_id = uuid.UUID("44444444-4444-4444-4444-444444444444")

        await ensure_user_and_profile(session, user_id, "ticket_emp@company.com", "Ticket Employee", "EMPLOYEE", "Sales")
        await ensure_user_and_profile(session, admin_id, "ticket_admin@company.com", "Ticket Admin", "HR_ADMIN", "HR")

        await session.commit()


def get_auth_header(
    user_id: str = "33333333-3333-3333-3333-333333333333",
    email: str = "ticket_emp@company.com",
    role: str = "EMPLOYEE",
    department: str = "Sales",
) -> dict:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "department": department,
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


def test_list_tickets_unauthenticated_returns_401():
    response = client.get("/api/v1/tickets")
    assert response.status_code == 401


def test_list_tickets_invalid_token_returns_401():
    headers = {"Authorization": "Bearer invalid_token_xyz"}
    response = client.get("/api/v1/tickets", headers=headers)
    assert response.status_code == 401


def test_create_ticket_unauthenticated_returns_401():
    payload = {"user_query": "Hỏi về chế độ bảo hiểm xã hội"}
    response = client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 401


def test_create_and_list_ticket_flow():
    headers = get_auth_header()
    payload = {
        "user_query": "Hỏi về quy trình xin nghỉ phép năm dài ngày",
        "escalate_reason": "user_requested_human",
        "target_department": "HRBP",
        "priority": "High",
    }
    # 1. Create Ticket
    create_res = client.post("/api/v1/tickets", headers=headers, json=payload)
    assert create_res.status_code == 201
    res_json = create_res.json()
    assert res_json["success"] is True
    data = res_json["data"]
    assert "ticket_code" in data
    assert data["ticket_code"].startswith("TCK-")
    assert data["employee_question"] == payload["user_query"]
    assert data["status"] == "open"
    assert data["priority"] == "High"
    assert data["target_department"] == "HRBP"

    ticket_id = data["id"]

    # 2. List Tickets as Employee
    list_res = client.get("/api/v1/tickets", headers=headers)
    assert list_res.status_code == 200
    list_data = list_res.json()["data"]
    assert isinstance(list_data, list)
    assert any(t["id"] == ticket_id for t in list_data)

    # 3. Get Detail as Employee
    detail_res = client.get(f"/api/v1/tickets/{ticket_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["id"] == ticket_id


def test_update_ticket_by_admin():
    # Employee creates a ticket
    emp_headers = get_auth_header()
    payload = {
        "user_query": "Hỏi về thời hạn thanh toán thưởng Tết",
        "target_department": "CB",
    }
    create_res = client.post("/api/v1/tickets", headers=emp_headers, json=payload)
    assert create_res.status_code == 201
    ticket_id = create_res.json()["data"]["id"]

    # Employee tries to update -> Forbidden 403
    patch_payload = {"status": "resolved", "resolution_note": "Tự giải quyết"}
    emp_update_res = client.patch(f"/api/v1/tickets/{ticket_id}", headers=emp_headers, json=patch_payload)
    assert emp_update_res.status_code == 403

    # Admin updates ticket status -> Success 200
    admin_headers = get_auth_header(
        user_id="44444444-4444-4444-4444-444444444444",
        email="ticket_admin@company.com",
        role="HR_ADMIN",
        department="HR",
    )
    admin_update_res = client.patch(f"/api/v1/tickets/{ticket_id}", headers=admin_headers, json=patch_payload)
    assert admin_update_res.status_code == 200
    updated_data = admin_update_res.json()["data"]
    assert updated_data["status"] == "resolved"
    assert updated_data["resolution_note"] == "Tự giải quyết"
    assert updated_data["resolved_at"] is not None

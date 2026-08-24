import uuid

import pytest_asyncio
from app.core.security import create_access_token
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB

from tests.conftest import TestingSessionLocal, client

SUPER_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
HR_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
TARGET_ID = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_access_admin_data():
    async with TestingSessionLocal() as db:
        for user_id, email, role, department in (
            (SUPER_ID, "access-super@company.com", "SUPER_ADMIN", "IT"),
            (HR_ID, "access-hr@company.com", "DEPARTMENT_MANAGER", "HR"),
            (TARGET_ID, "access-target@company.com", "EMPLOYEE", "SALES"),
        ):
            if await db.get(UserDB, user_id) is None:
                user = UserDB(id=user_id, email=email, hashed_password="hash")
                user.profile = ProfileDB(id=user_id, display_name=email.split("@")[0], role=role, department=department)
                db.add(user)
        await db.commit()


def header(user_id: uuid.UUID, claimed_role: str) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id), "email": "access@company.com", "role": claimed_role, "department": "FORGED"})
    return {"Authorization": f"Bearer {token}"}


def test_access_model_and_users_are_db_authorized():
    response = client.get("/api/v1/admin/access-model", headers=header(SUPER_ID, "EMPLOYEE"))
    users = client.get("/api/v1/admin/users", headers=header(SUPER_ID, "EMPLOYEE"))
    assert response.status_code == 200
    assert "SUPER_ADMIN" in response.json()["data"]["roles"]
    assert users.status_code == 200
    assert any(item["user_id"] == str(TARGET_ID) for item in users.json()["data"])


def test_super_admin_updates_access_and_writes_audit_using_db_role():
    response = client.patch(
        f"/api/v1/admin/users/{TARGET_ID}/access",
        headers=header(SUPER_ID, "EMPLOYEE"),
        json={"role": "DEPARTMENT_MANAGER", "department": "Engineering"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "DEPARTMENT_MANAGER"
    audit = client.get("/api/v1/admin/audit-logs", headers=header(SUPER_ID, "EMPLOYEE"))
    assert audit.status_code == 200
    entry = next(item for item in audit.json()["data"] if item["resource_id"] == str(TARGET_ID))
    assert entry["action"] == "USER_ACCESS_UPDATED"
    assert entry["before"]["role"] == "EMPLOYEE"
    assert entry["after"]["department"] == "Engineering"


def test_forged_super_admin_claim_cannot_escalate_department_manager():
    response = client.patch(
        f"/api/v1/admin/users/{TARGET_ID}/access",
        headers=header(HR_ID, "SUPER_ADMIN"),
        json={"role": "SUPER_ADMIN", "department": "IT"},
    )
    assert response.status_code == 403
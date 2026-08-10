import uuid

import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.conversations import ConversationDB
from app.domain.models.documents import DocumentDB
from app.domain.models.messages import MessageDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB

from tests.conftest import TestingSessionLocal, client


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_citations_test_data():
    async with TestingSessionLocal() as session:
        user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        admin_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

        user = await session.get(UserDB, user_id)
        if not user:
            user = UserDB(
                id=user_id,
                email="user1@company.com",
                hashed_password=hash_password("password123"),
            )
            user.profile = ProfileDB(
                id=user_id,
                display_name="User One",
                role="EMPLOYEE",
                department="Engineering",
            )
            session.add(user)

        admin = await session.get(UserDB, admin_id)
        if not admin:
            admin = UserDB(
                id=admin_id,
                email="hr_admin@company.com",
                hashed_password=hash_password("password123"),
            )
            admin.profile = ProfileDB(
                id=admin_id,
                display_name="HR Admin",
                role="HR_ADMIN",
                department="HR",
            )
            session.add(admin)

        # Restricted Confidential Document
        restricted_doc = DocumentDB(
            id=uuid.uuid4(),
            title="Chính sách bảo mật tài chính",
            source_file="financial_policy.pdf",
            category="FINANCE",
            version="3.0",
            effective_date="2026-01-01",
            confidentiality="RESTRICTED",
            status="ACTIVE",
            uploaded_by=admin_id,
        )
        session.add(restricted_doc)

        conv = ConversationDB(
            id=uuid.uuid4(),
            user_id=user_id,
            title="Cit Conv",
            state="ACTIVE",
        )
        session.add(conv)

        # Message with citation referencing restricted document
        msg = MessageDB(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            role="ASSISTANT",
            content="Nội dung bảo mật",
            citations=[
                {
                    "citation_id": "cit_restricted_999",
                    "title": "Chính sách bảo mật tài chính",
                    "page": 1,
                    "section": "Điều 1",
                }
            ],
        )
        session.add(msg)

        normal_msg = MessageDB(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            role="ASSISTANT",
            content="Normal citation",
            citations=[
                {
                    "citation_id": "cit_01",
                    "title": "HR Policy",
                    "source_file": "hr_policy.pdf",
                    "page": 5,
                    "chunk_id": "hr-policy::0001",
                    "excerpt": "Policy excerpt",
                }
            ],
        )
        session.add(normal_msg)

        await session.commit()


def get_auth_header(
    user_id: str = "11111111-1111-1111-1111-111111111111",
    email: str = "user1@company.com",
    role: str = "EMPLOYEE",
) -> dict:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "department": "Engineering",
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


def test_get_citation_detail_success():
    headers = get_auth_header()
    citation_id = "cit_01"

    response = client.get(f"/api/v1/citations/{citation_id}", headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["citation_id"] == citation_id
    assert "document" in res_data["data"]
    assert "location" in res_data["data"]
    assert "excerpt" in res_data["data"]
    assert res_data["data"]["conflict_warning"] is False


def test_get_citation_detail_not_found():
    headers = get_auth_header()
    invalid_cit_id = "invalid_unknown_9999"

    response = client.get(f"/api/v1/citations/{invalid_cit_id}", headers=headers)
    assert response.status_code == 404
    res_data = response.json()
    assert res_data["success"] is False
    assert res_data["error"]["code"] == "CITATION_NOT_FOUND"


def test_get_citation_detail_access_denied():
    headers = get_auth_header(role="EMPLOYEE")
    restricted_cit_id = "cit_restricted_999"

    response = client.get(f"/api/v1/citations/{restricted_cit_id}", headers=headers)
    assert response.status_code == 403
    res_data = response.json()
    assert res_data["success"] is False
    assert res_data["error"]["code"] == "DOCUMENT_ACCESS_DENIED"

import pytest
from app.core.knowledge_db import (
    create_all_tables,
    create_knowledge_engine,
    drop_all_tables,
    get_knowledge_session as get_session,
)
from app.core.security import create_access_token
from app.domain.models.knowledge import ReviewStatus
from app.services.knowledge_service import KnowledgeRepository, log_audit
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_knowledge_db():
    engine = create_knowledge_engine("sqlite:///:memory:")
    drop_all_tables(engine)
    create_all_tables(engine)

    with get_session(engine) as session:
        repo = KnowledgeRepository(session)
        repo.create_tenant(tenant_id="nexatech", slug="nexatech", name="NexaTech Corporation")
        doc = repo.create_document(
            tenant_id="nexatech",
            document_code="12_quy-che-cong-tac-phi.md",
            title="Quy chế Công tác phí và Phụ cấp Di chuyển",
            document_domain="COMPANY_POLICY",
            access_scope="COMPANY_WIDE",
            owner_department="GENERAL",
        )
        ver = repo.create_version(
            tenant_id="nexatech",
            document_id=doc.document_id,
            version_number="1.0",
            raw_content="Quy định hạn mức khách sạn tại HN/HCM là 800.000 VNĐ.",
        )
        chunk = repo.create_chunk(
            tenant_id="nexatech",
            version_id=ver.version_id,
            chunk_index=1,
            chunk_text="Hạn mức khách sạn 800.000 VNĐ.",
        )
        k_item = repo.create_knowledge_item(
            tenant_id="nexatech",
            version_id=ver.version_id,
            item_type="POLICY_RULE",
            statement="Hạn mức khách sạn nhân viên là 800.000 VNĐ/đêm",
            subject="khách_sạn",
            predicate="hạn_mức_phòng_đêm",
            object_value="800000 VND",
            value_numeric=800000,
            review_status=ReviewStatus.CANDIDATE.value,
        )
        repo.create_evidence(
            tenant_id="nexatech",
            knowledge_id=k_item.knowledge_id,
            chunk_id=chunk.chunk_id,
            exact_quote_span="Hạn mức khách sạn 800.000 VNĐ.",
            start_char=0,
            end_char=30,
        )

        doc2 = repo.create_document(
            tenant_id="nexatech",
            document_code="mgt_dec_04.md",
            title="Quyết định số 04 điều chỉnh hạn mức chi tiêu",
            document_domain="MANAGEMENT_DECISION",
        )
        ver2 = repo.create_version(
            tenant_id="nexatech",
            document_id=doc2.document_id,
            version_number="1.0",
            raw_content="Điều chỉnh hạn mức khách sạn HCM lên 1.200.000 VNĐ.",
        )
        k_item2 = repo.create_knowledge_item(
            tenant_id="nexatech",
            version_id=ver2.version_id,
            item_type="DECISION",
            statement="Hạn mức khách sạn nhân viên tại HCM là 1.200.000 VNĐ/đêm",
            subject="khách_sạn",
            predicate="hạn_mức_phòng_đêm",
            object_value="1200000 VND",
            value_numeric=1200000,
            review_status=ReviewStatus.CANDIDATE.value,
        )
        repo.create_relation(
            tenant_id="nexatech",
            source_knowledge_id=k_item2.knowledge_id,
            target_knowledge_id=k_item.knowledge_id,
            relation_type="MODIFIES",
            explanation="Điều chỉnh hạn mức từ 800k lên 1.2M",
        )

        log_audit(
            session=session,
            tenant_id="nexatech",
            actor_user_id="admin_1",
            actor_role="SUPER_ADMIN",
            action="BOOTSTRAP",
            entity_type="tenant",
            entity_id="nexatech",
            payload={"status": "INITIALIZED"},
        )

    yield engine
    drop_all_tables(engine)


import uuid
import pytest_asyncio
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from tests.conftest import TestingSessionLocal

ADMIN_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
EMP_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_auth_users():
    async with TestingSessionLocal() as db:
        for u_id, email, role, dept in (
            (ADMIN_ID, "admin@nexatech.com", "SUPER_ADMIN", "IT"),
            (EMP_ID, "emp@nexatech.com", "EMPLOYEE", "SALES"),
        ):
            if await db.get(UserDB, u_id) is None:
                u = UserDB(id=u_id, email=email, hashed_password="hash")
                u.profile = ProfileDB(id=u_id, display_name=email.split("@")[0], role=role, department=dept)
                db.add(u)
        await db.commit()


@pytest.fixture
def admin_headers():
    token = create_access_token(
        {"sub": str(ADMIN_ID), "email": "admin@nexatech.com", "role": "SUPER_ADMIN", "department": "IT"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def employee_headers():
    token = create_access_token(
        {"sub": str(EMP_ID), "email": "emp@nexatech.com", "role": "EMPLOYEE", "department": "SALES"}
    )
    return {"Authorization": f"Bearer {token}"}


def test_list_knowledge_items(employee_headers):
    response = client.get("/api/v1/knowledge/items?tenant_id=nexatech", headers=employee_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1


def test_get_knowledge_item_detail(employee_headers):
    list_res = client.get("/api/v1/knowledge/items?tenant_id=nexatech", headers=employee_headers)
    items = list_res.json()["data"]
    item_id = items[0]["knowledge_id"]

    detail_res = client.get(f"/api/v1/knowledge/items/{item_id}?tenant_id=nexatech", headers=employee_headers)
    assert detail_res.status_code == 200
    detail_data = detail_res.json()["data"]
    assert detail_data["item"]["knowledge_id"] == item_id
    assert isinstance(detail_data["evidences"], list)


def test_approve_knowledge_item(admin_headers, employee_headers):
    list_res = client.get("/api/v1/knowledge/items?tenant_id=nexatech", headers=employee_headers)
    items = list_res.json()["data"]
    item_id = items[0]["knowledge_id"]

    # Employee cannot approve
    emp_res = client.patch(f"/api/v1/knowledge/items/{item_id}/approve?tenant_id=nexatech", headers=employee_headers)
    assert emp_res.status_code == 403

    # Admin approves
    admin_res = client.patch(f"/api/v1/knowledge/items/{item_id}/approve?tenant_id=nexatech", headers=admin_headers)
    assert admin_res.status_code == 200
    assert admin_res.json()["data"]["review_status"] == "APPROVED"


def test_reject_knowledge_item(admin_headers, employee_headers):
    list_res = client.get("/api/v1/knowledge/items?tenant_id=nexatech", headers=employee_headers)
    items = list_res.json()["data"]
    item_id = items[-1]["knowledge_id"]

    reject_res = client.patch(
        f"/api/v1/knowledge/items/{item_id}/reject?tenant_id=nexatech",
        json={"reason": "Duplicated or outdated rule"},
        headers=admin_headers,
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["data"]["review_status"] == "REJECTED"


def test_edit_knowledge_item(admin_headers, employee_headers):
    list_res = client.get("/api/v1/knowledge/items?tenant_id=nexatech", headers=admin_headers)
    items = list_res.json()["data"]
    item_id = items[0]["knowledge_id"]

    edit_res = client.patch(
        f"/api/v1/knowledge/items/{item_id}/edit?tenant_id=nexatech",
        json={
            "object_value": "1500000 VND",
            "value_numeric": 1500000.0,
            "role_scope": ["MANAGER", "DIRECTOR"],
            "review_notes": "Corrected by admin",
        },
        headers=admin_headers,
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["data"]["review_status"] == "APPROVED"
    detail_res = client.get(f"/api/v1/knowledge/items/{item_id}", headers=admin_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["item"]["role_scope"] == ["MANAGER", "DIRECTOR"]


def test_cross_tenant_access_is_denied(employee_headers):
    response = client.get("/api/v1/knowledge/items?tenant_id=another-company", headers=employee_headers)
    assert response.status_code == 403


def test_list_and_approve_relations(admin_headers, employee_headers):
    rel_res = client.get("/api/v1/knowledge/relations?tenant_id=nexatech", headers=employee_headers)
    assert rel_res.status_code == 200
    relations = rel_res.json()["data"]
    if relations:
        rel_id = relations[0]["relation_id"]
        app_res = client.patch(
            f"/api/v1/knowledge/relations/{rel_id}/approve?tenant_id=nexatech", headers=admin_headers
        )
        assert app_res.status_code == 200
        assert app_res.json()["data"]["status"] == "ACTIVE"


def test_audit_trail(admin_headers, employee_headers):
    # Employee cannot view audit trail
    emp_res = client.get("/api/v1/knowledge/audit?tenant_id=nexatech", headers=employee_headers)
    assert emp_res.status_code == 403

    # Admin can view audit trail
    admin_res = client.get("/api/v1/knowledge/audit?tenant_id=nexatech", headers=admin_headers)
    assert admin_res.status_code == 200
    logs = admin_res.json()["data"]
    assert isinstance(logs, list)
    assert len(logs) >= 1

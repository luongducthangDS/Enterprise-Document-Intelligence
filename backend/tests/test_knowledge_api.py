import pytest
from app.core.security import create_access_token
from fastapi.testclient import TestClient
from main import app

from src.knowledge.database import create_all_tables, create_knowledge_engine, drop_all_tables, get_session
from src.knowledge.models import ReviewStatus
from src.knowledge.service import KnowledgeService

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_knowledge_db():
    engine = create_knowledge_engine("sqlite:///:memory:")
    drop_all_tables(engine)
    create_all_tables(engine)

    with get_session(engine) as session:
        service = KnowledgeService(session)
        service.bootstrap_target_slice(
            tenant_id="nexatech",
            initial_review_status=ReviewStatus.CANDIDATE.value,
        )
        from src.knowledge.audit import log_audit
        log_audit(
            session=session,
            tenant_id="nexatech",
            actor_user_id="admin_1",
            actor_role="ADMIN",
            action="BOOTSTRAP",
            entity_type="tenant",
            entity_id="nexatech",
            payload={"status": "INITIALIZED"},
        )

    yield engine
    drop_all_tables(engine)


@pytest.fixture
def admin_headers():
    token = create_access_token({"sub": "admin_1", "email": "admin@nexatech.com", "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def employee_headers():
    token = create_access_token({"sub": "emp_1", "email": "emp@nexatech.com", "role": "EMPLOYEE"})
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
    list_res = client.get("/api/v1/knowledge/items?tenant_id=nexatech", headers=employee_headers)
    items = list_res.json()["data"]
    item_id = items[0]["knowledge_id"]

    edit_res = client.patch(
        f"/api/v1/knowledge/items/{item_id}/edit?tenant_id=nexatech",
        json={"object_value": "1500000 VND", "value_numeric": 1500000.0, "review_notes": "Corrected by admin"},
        headers=admin_headers,
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["data"]["review_status"] == "APPROVED"


def test_list_and_approve_relations(admin_headers, employee_headers):
    rel_res = client.get("/api/v1/knowledge/relations?tenant_id=nexatech", headers=employee_headers)
    assert rel_res.status_code == 200
    relations = rel_res.json()["data"]
    if relations:
        rel_id = relations[0]["relation_id"]
        app_res = client.patch(f"/api/v1/knowledge/relations/{rel_id}/approve?tenant_id=nexatech", headers=admin_headers)
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

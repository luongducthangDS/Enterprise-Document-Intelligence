import io
import uuid

import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB

from tests.conftest import TestingSessionLocal, client


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_documents_test_data():
    async with TestingSessionLocal() as session:
        admin_id = uuid.UUID("88888888-8888-8888-8888-888888888888")
        user_id = uuid.UUID("77777777-7777-7777-7777-777777777777")

        admin = await session.get(UserDB, admin_id)
        if not admin:
            admin = UserDB(
                id=admin_id,
                email="doc_admin@company.com",
                hashed_password=hash_password("password123"),
            )
            admin.profile = ProfileDB(
                id=admin_id,
                display_name="Doc Admin",
                role="SUPER_ADMIN",
                department="HR",
            )
            session.add(admin)

        admin_profile = await session.get(ProfileDB, admin_id)
        if admin_profile:
            admin_profile.role = "SUPER_ADMIN"
            admin_profile.department = "HR"

        user = await session.get(UserDB, user_id)
        if not user:
            user = UserDB(
                id=user_id,
                email="doc_user@company.com",
                hashed_password=hash_password("password123"),
            )
            user.profile = ProfileDB(
                id=user_id,
                display_name="Doc User",
                role="EMPLOYEE",
                department="Engineering",
            )
            session.add(user)

        await session.commit()


def get_auth_header(
    user_id: str = "88888888-8888-8888-8888-888888888888",
    email: str = "doc_admin@company.com",
    role: str = "SUPER_ADMIN",
) -> dict:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "department": "HR",
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


def test_upload_document_success():
    headers = get_auth_header()
    file_content = b"%PDF-1.4 Mock HR Policy document text content for testing"
    files = {"file": ("chinh_sach_nghi_phep.pdf", io.BytesIO(file_content), "application/pdf")}
    data = {
        "title": "Chính sách nghỉ phép 2026",
        "category": "HR_POLICY",
        "version": "1.0",
        "effective_date": "2026-01-01",
        "confidentiality": "INTERNAL",
        "access_scope": "COMPANY_WIDE",
    }

    response = client.post("/api/v1/documents", headers=headers, files=files, data=data)
    assert response.status_code == 201
    res = response.json()
    assert res["success"] is True
    assert "document_id" in res["data"]
    assert "ingestion_job_id" in res["data"]
    assert res["data"]["status"] == "ACTIVE"
    assert res["data"]["access_scope"] == "COMPANY_WIDE"


def test_upload_document_uses_database_super_admin_role():
    headers = get_auth_header(role="super_admin")
    files = {"file": ("legacy_admin.pdf", io.BytesIO(b"%PDF-1.4 Legacy admin"), "application/pdf")}

    response = client.post("/api/v1/documents", headers=headers, files=files)

    assert response.status_code == 201


def test_employee_cannot_upload_or_list_documents():
    headers = get_auth_header(
        user_id="77777777-7777-7777-7777-777777777777",
        email="doc_user@company.com",
        role="EMPLOYEE",
    )
    files = {"file": ("forbidden.pdf", io.BytesIO(b"%PDF-1.4 Forbidden"), "application/pdf")}

    upload_response = client.post("/api/v1/documents", headers=headers, files=files)
    list_response = client.get("/api/v1/documents", headers=headers)

    assert upload_response.status_code == 403
    assert list_response.status_code == 403


def test_upload_document_unsupported_type():
    headers = get_auth_header()
    file_content = b"Binary data executable"
    files = {"file": ("malicious.exe", io.BytesIO(file_content), "application/octet-stream")}

    response = client.post("/api/v1/documents", headers=headers, files=files)
    assert response.status_code == 415
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_document_empty_file():
    headers = get_auth_header()
    file_content = b""
    files = {"file": ("empty.pdf", io.BytesIO(file_content), "application/pdf")}

    response = client.post("/api/v1/documents", headers=headers, files=files)
    assert response.status_code == 422
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "FILE_NOT_MACHINE_READABLE"


def test_list_documents():
    headers = get_auth_header()
    response = client.get("/api/v1/documents", headers=headers)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert isinstance(res["data"], list)
    assert len(res["data"]) > 0
    assert "pagination" in res["meta"]


def test_get_document_detail():
    headers = get_auth_header()
    # First create a document
    file_content = b"%PDF-1.4 Detail Test Document Content"
    files = {"file": ("detail_doc.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_res = client.post("/api/v1/documents", headers=headers, files=files)
    doc_id = upload_res.json()["data"]["document_id"]

    response = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["document_id"] == doc_id
    assert "ingestion" in res["data"]
    assert "index" in res["data"]


def test_update_document_metadata_success():
    headers = get_auth_header(role="SUPER_ADMIN")
    file_content = b"%PDF-1.4 Metadata Update Test Content"
    files = {"file": ("meta_doc.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_res = client.post("/api/v1/documents", headers=headers, files=files)
    doc_id = upload_res.json()["data"]["document_id"]

    patch_payload = {
        "title": "Tên tài liệu mới cập nhật",
        "category": "BENEFITS",
        "version": "2.0",
    }
    response = client.patch(f"/api/v1/documents/{doc_id}/metadata", headers=headers, json=patch_payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["metadata_updated"] is True
    assert res["data"]["requires_reindex"] is True


def test_update_document_metadata_forbidden():
    employee_headers = get_auth_header(
        user_id="77777777-7777-7777-7777-777777777777",
        email="doc_user@company.com",
        role="EMPLOYEE",
    )
    admin_headers = get_auth_header(role="SUPER_ADMIN")
    file_content = b"%PDF-1.4 Employee Edit Test Content"
    files = {"file": ("emp_doc.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_res = client.post("/api/v1/documents", headers=admin_headers, files=files)
    doc_id = upload_res.json()["data"]["document_id"]

    patch_payload = {"title": "Attempt Unauthorized Update"}
    response = client.patch(f"/api/v1/documents/{doc_id}/metadata", headers=employee_headers, json=patch_payload)
    assert response.status_code == 403
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "FORBIDDEN"


def test_archive_document_and_conflict():
    headers = get_auth_header(role="SUPER_ADMIN")
    file_content = b"%PDF-1.4 Archive Test Content"
    files = {"file": ("archive_doc.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_res = client.post("/api/v1/documents", headers=headers, files=files)
    doc_id = upload_res.json()["data"]["document_id"]

    # First archive call
    archive_req = {"reason": "Superseded by new policy"}
    response = client.post(f"/api/v1/documents/{doc_id}/archive", headers=headers, json=archive_req)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["status"] == "ARCHIVED"

    # Second archive call (Conflict)
    response_conflict = client.post(f"/api/v1/documents/{doc_id}/archive", headers=headers, json=archive_req)
    assert response_conflict.status_code == 409
    res_conflict = response_conflict.json()
    assert res_conflict["success"] is False
    assert res_conflict["error"]["code"] == "DOCUMENT_STATUS_CONFLICT"


def test_get_ingestion_job_status():
    headers = get_auth_header()
    file_content = b"%PDF-1.4 Ingestion Job Status Test Content"
    files = {"file": ("ingest_doc.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_res = client.post("/api/v1/documents", headers=headers, files=files)
    job_id = upload_res.json()["data"]["ingestion_job_id"]

    response = client.get(f"/api/v1/ingestion-jobs/{job_id}", headers=headers)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["job_id"] == job_id
    assert res["data"]["state"] in ("QUEUED", "PROCESSING", "COMPLETED")


def test_get_ingestion_job_not_found():
    headers = get_auth_header()
    fake_job_id = str(uuid.uuid4())

    response = client.get(f"/api/v1/ingestion-jobs/{fake_job_id}", headers=headers)
    assert response.status_code == 404
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "INGESTION_JOB_NOT_FOUND"

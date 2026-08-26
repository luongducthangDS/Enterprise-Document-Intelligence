import io
import uuid

import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.services.document_submission_service import DocumentSubmissionService

from tests.conftest import TestingSessionLocal, client

ADMIN_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
EMPLOYEE_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_submission_users():
    async with TestingSessionLocal() as session:
        for user_id, email, role, department in [
            (ADMIN_ID, "review-admin@company.com", "SUPER_ADMIN", "HR"),
            (EMPLOYEE_ID, "review-user@company.com", "EMPLOYEE", "HR"),
        ]:
            user = await session.get(UserDB, user_id)
            if user is None:
                user = UserDB(id=user_id, email=email, hashed_password=hash_password("password123"))
                user.profile = ProfileDB(
                    id=user_id,
                    display_name=email,
                    role=role,
                    department=department,
                )
                session.add(user)
        await session.commit()


def auth_header(user_id: uuid.UUID, email: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + create_access_token(
            {"sub": str(user_id), "email": email, "role": "IGNORED", "department": "IGNORED"}
        )
    }


class CompletedAnalysisWorker:
    async def submit_document_analysis(self, payload: dict) -> dict:
        assert payload["publication_status"] == "draft"
        assert payload["artifact_state"] == "draft"
        assert payload["retrieval_enabled"] is False
        return {"job_id": payload["job_id"], "state": "QUEUED"}

    async def get_status(self, job_id: str) -> dict:
        return {
            "job_id": job_id,
            "kind": "DOCUMENT_ANALYSIS",
            "state": "COMPLETED",
            "stage": "COMPLETED",
            "progress_percent": 100,
            "result": {
                "extract_method": "PDF_TEXT",
                "extracted_text": "Nội dung đã được trích xuất để người duyệt kiểm tra.",
                "chunk_count": 1,
                "chunks": [
                    {
                        "chunk_index": 0,
                        "content": "Nội dung đã được trích xuất để người duyệt kiểm tra.",
                        "heading_path": "",
                        "page_start": 1,
                        "page_end": 1,
                        "char_count": 54,
                    }
                ],
                "warnings": [],
            },
            "error": None,
        }


def test_upload_is_staged_then_approval_creates_official_document():
    headers = auth_header(ADMIN_ID, "review-admin@company.com")
    filename = "pending_review_policy.pdf"
    previous = (DocumentSubmissionService.worker_client, DocumentSubmissionService.worker_dispatch_enabled)
    DocumentSubmissionService.worker_client = CompletedAnalysisWorker()
    DocumentSubmissionService.worker_dispatch_enabled = True
    try:
        response = client.post(
            "/api/v1/document-submissions",
            headers=headers,
            files={"file": (filename, io.BytesIO(b"%PDF-1.4 review workflow"), "application/pdf")},
            data={
                "title": "Chính sách đang chờ duyệt",
                "category": "HR_POLICY",
                "department": "HR",
                "access_scope": "DEPARTMENT",
            },
        )
        assert response.status_code == 201
        submission_id = response.json()["data"]["submission_id"]

        before = client.get("/api/v1/documents", headers=headers)
        assert all(item["title"] != "Chính sách đang chờ duyệt" for item in before.json()["data"])

        detail = client.get(f"/api/v1/document-submissions/{submission_id}", headers=headers)
        assert detail.status_code == 200
        payload = detail.json()["data"]
        assert payload["status"] == "PENDING_REVIEW"
        assert payload["analysis"]["extracted_text"].startswith("Nội dung")
        assert payload["analysis"]["chunk_count"] == 1

        approved = client.post(
            f"/api/v1/document-submissions/{submission_id}/approve",
            headers=headers,
            json={"note": "Đã kiểm tra extract"},
        )
        assert approved.status_code == 200
        assert approved.json()["data"]["status"] == "PUBLISHING"
        assert approved.json()["data"]["published_document_id"]

        after = client.get("/api/v1/documents", headers=headers)
        assert any(item["title"] == "Chính sách đang chờ duyệt" for item in after.json()["data"])
    finally:
        DocumentSubmissionService.worker_client, DocumentSubmissionService.worker_dispatch_enabled = previous


def test_employee_cannot_create_submission():
    headers = auth_header(EMPLOYEE_ID, "review-user@company.com")
    response = client.post(
        "/api/v1/document-submissions",
        headers=headers,
        files={"file": ("forbidden-review.pdf", io.BytesIO(b"%PDF-1.4 forbidden"), "application/pdf")},
    )
    assert response.status_code == 403


def test_rejected_submission_never_becomes_official():
    headers = auth_header(ADMIN_ID, "review-admin@company.com")
    previous = (DocumentSubmissionService.worker_client, DocumentSubmissionService.worker_dispatch_enabled)
    DocumentSubmissionService.worker_client = CompletedAnalysisWorker()
    DocumentSubmissionService.worker_dispatch_enabled = True
    try:
        created = client.post(
            "/api/v1/document-submissions",
            headers=headers,
            files={"file": ("rejected-policy.pdf", io.BytesIO(b"%PDF-1.4 rejected"), "application/pdf")},
            data={"department": "HR", "access_scope": "RESTRICTED"},
        ).json()["data"]
        client.get(f"/api/v1/document-submissions/{created['submission_id']}", headers=headers)
        rejected = client.post(
            f"/api/v1/document-submissions/{created['submission_id']}/reject",
            headers=headers,
            json={"note": "Extract chưa đạt"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["data"]["status"] == "REJECTED"
        documents = client.get("/api/v1/documents", headers=headers).json()["data"]
        assert all(item["title"] != "rejected-policy.pdf" for item in documents)
    finally:
        DocumentSubmissionService.worker_client, DocumentSubmissionService.worker_dispatch_enabled = previous


def test_update_public_url_on_submission_and_document():
    headers = auth_header(ADMIN_ID, "review-admin@company.com")
    previous = (DocumentSubmissionService.worker_client, DocumentSubmissionService.worker_dispatch_enabled)
    DocumentSubmissionService.worker_client = CompletedAnalysisWorker()
    DocumentSubmissionService.worker_dispatch_enabled = True
    try:
        created = client.post(
            "/api/v1/document-submissions",
            headers=headers,
            files={"file": ("public_url_policy.pdf", io.BytesIO(b"%PDF-1.4 public url test"), "application/pdf")},
            data={"title": "Tài liệu test Cloudinary URL", "department": "HR", "access_scope": "RESTRICTED"},
        ).json()["data"]
        sub_id = created["submission_id"]

        # Update public_url on submission
        cloud_url = "https://res.cloudinary.com/test-cloud/image/upload/v12345/public_url_policy.pdf"
        patch_res = client.patch(
            f"/api/v1/document-submissions/{sub_id}/public-url",
            headers=headers,
            json={"public_url": cloud_url},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["data"]["public_url"] == cloud_url

        # Approve and check if public_url propagates to official document
        client.get(f"/api/v1/document-submissions/{sub_id}", headers=headers)
        approved = client.post(
            f"/api/v1/document-submissions/{sub_id}/approve",
            headers=headers,
            json={"note": "Approved with Cloudinary URL"},
        )
        assert approved.status_code == 200
        doc_id = approved.json()["data"]["published_document_id"]

        # Verify document detail has public_url
        doc_detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert doc_detail.status_code == 200
        assert doc_detail.json()["data"]["public_url"] == cloud_url

        # Update document public_url directly
        new_cloud_url = "https://res.cloudinary.com/test-cloud/image/upload/v67890/public_url_policy_v2.pdf"
        patch_doc = client.patch(
            f"/api/v1/documents/{doc_id}/public-url",
            headers=headers,
            json={"public_url": new_cloud_url},
        )
        assert patch_doc.status_code == 200
        assert patch_doc.json()["data"]["public_url"] == new_cloud_url
    finally:
        DocumentSubmissionService.worker_client, DocumentSubmissionService.worker_dispatch_enabled = previous


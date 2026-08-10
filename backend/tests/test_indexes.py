import uuid

import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.documents import DocumentDB
from app.domain.models.index_job import IndexJobDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB

from tests.conftest import TestingSessionLocal, client


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_indexes_test_data():
    async with TestingSessionLocal() as session:
        admin_id = uuid.UUID("66666666-6666-6666-6666-666666666666")
        doc_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
        archived_doc_id = uuid.UUID("44444444-4444-4444-4444-444444444444")

        admin = await session.get(UserDB, admin_id)
        if not admin:
            admin = UserDB(
                id=admin_id,
                email="idx_admin@company.com",
                hashed_password=hash_password("password123"),
            )
            admin.profile = ProfileDB(
                id=admin_id,
                display_name="Index Admin",
                role="HR_ADMIN",
                department="HR",
            )
            session.add(admin)

        doc = await session.get(DocumentDB, doc_id)
        if not doc:
            doc = DocumentDB(
                id=doc_id,
                title="Tài liệu index test",
                source_file="index_test.pdf",
                status="ACTIVE",
                uploaded_by=admin_id,
            )
            session.add(doc)

        archived_doc = await session.get(DocumentDB, archived_doc_id)
        if not archived_doc:
            archived_doc = DocumentDB(
                id=archived_doc_id,
                title="Tài liệu cũ đã lưu trữ",
                source_file="old_policy.pdf",
                status="ARCHIVED",
                uploaded_by=admin_id,
            )
            session.add(archived_doc)

        await session.commit()


def get_auth_header(
    user_id: str = "66666666-6666-6666-6666-666666666666",
    email: str = "idx_admin@company.com",
    role: str = "HR_ADMIN",
) -> dict:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "department": "HR",
    }
    token = create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


def test_create_index_rebuild_success():
    headers = get_auth_header()
    payload = {
        "document_ids": ["55555555-5555-5555-5555-555555555555"],
        "strategy": "REPLACE",
    }

    response = client.post("/api/v1/indexes/rebuilds", headers=headers, json=payload)
    assert response.status_code == 202
    res = response.json()
    assert res["success"] is True
    assert "job_id" in res["data"]
    assert res["data"]["state"] == "QUEUED"
    assert res["data"]["poll_after_ms"] == 2000


def test_create_index_rebuild_conflict():
    headers = get_auth_header()
    payload = {
        "document_ids": None,
        "strategy": "INCREMENTAL",
    }

    # Should fail because previous test created a job that is QUEUED
    response = client.post("/api/v1/indexes/rebuilds", headers=headers, json=payload)
    assert response.status_code == 409
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "INDEX_REBUILD_IN_PROGRESS"


def test_create_index_rebuild_document_not_ready():
    headers = get_auth_header()

    # Manually mark all active index jobs completed to bypass conflict check for this test
    async def set_jobs_completed():
        async with TestingSessionLocal() as session:
            res = await session.execute(IndexJobDB.__table__.select())
            jobs = res.all()
            for job in jobs:
                await session.execute(
                    IndexJobDB.__table__.update()
                    .where(IndexJobDB.id == job.id)
                    .values(state="COMPLETED")
                )
            await session.commit()

    import asyncio
    asyncio.run(set_jobs_completed())

    payload = {
        "document_ids": ["44444444-4444-4444-4444-444444444444"],  # ARCHIVED doc
        "strategy": "REPLACE",
    }

    response = client.post("/api/v1/indexes/rebuilds", headers=headers, json=payload)
    assert response.status_code == 422
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "DOCUMENT_NOT_READY"


def test_get_index_rebuild_job_status():
    headers = get_auth_header()

    # Create a fresh job first
    async def set_jobs_completed():
        async with TestingSessionLocal() as session:
            await session.execute(
                IndexJobDB.__table__.update().values(state="COMPLETED")
            )
            await session.commit()

    import asyncio
    asyncio.run(set_jobs_completed())

    payload = {"document_ids": None, "strategy": "REPLACE"}
    create_res = client.post("/api/v1/indexes/rebuilds", headers=headers, json=payload)
    job_id = create_res.json()["data"]["job_id"]

    response = client.get(f"/api/v1/indexes/rebuilds/{job_id}", headers=headers)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["job_id"] == job_id
    assert res["data"]["active_index_version"] == "v1.0"


def test_get_index_rebuild_job_status_not_found():
    headers = get_auth_header()
    fake_job_id = str(uuid.uuid4())

    response = client.get(f"/api/v1/indexes/rebuilds/{fake_job_id}", headers=headers)
    assert response.status_code == 404
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "INDEX_JOB_NOT_FOUND"

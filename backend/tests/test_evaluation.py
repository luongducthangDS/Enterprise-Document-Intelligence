import uuid

import pytest_asyncio
from app.core.security import create_access_token, hash_password
from app.domain.models.evaluation import EvaluationRunDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB

from tests.conftest import TestingSessionLocal, client


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_evaluation_test_data():
    async with TestingSessionLocal() as session:
        admin_id = uuid.UUID("55555555-5555-5555-5555-555555555555")

        admin = await session.get(UserDB, admin_id)
        if not admin:
            admin = UserDB(
                id=admin_id,
                email="eval_admin@company.com",
                hashed_password=hash_password("password123"),
            )
            admin.profile = ProfileDB(
                id=admin_id,
                display_name="Eval Admin",
                role="SUPER_ADMIN",
                department="HR",
            )
            session.add(admin)

        admin_profile = await session.get(ProfileDB, admin_id)
        admin_profile.role = "SUPER_ADMIN"
        admin_profile.department = "HR"
        employee_id = uuid.UUID("51515151-5151-4515-8515-515151515151")
        if await session.get(UserDB, employee_id) is None:
            employee = UserDB(id=employee_id, email="eval_employee@company.com", hashed_password=hash_password("password123"))
            employee.profile = ProfileDB(id=employee_id, display_name="Eval Employee", role="EMPLOYEE", department="HR")
            session.add(employee)

        await session.commit()


def get_auth_header(
    user_id: str = "55555555-5555-5555-5555-555555555555",
    email: str = "eval_admin@company.com",
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


def test_create_evaluation_run_success():
    headers = get_auth_header()
    payload = {
        "dataset_id": "evalset_hr_v1",
        "index_version": "idxver_v1.0",
        "model_config_id": "modelcfg_01",
    }

    response = client.post("/api/v1/evaluation/runs", headers=headers, json=payload)
    assert response.status_code == 202
    res = response.json()
    assert res["success"] is True
    assert "run_id" in res["data"]
    assert res["data"]["state"] == "QUEUED"
    assert res["data"]["poll_after_ms"] == 3000


def test_employee_cannot_create_evaluation_run():
    headers = get_auth_header(user_id="51515151-5151-4515-8515-515151515151", email="eval_employee@company.com", role="EMPLOYEE")
    response = client.post(
        "/api/v1/evaluation/runs",
        headers=headers,
        json={"dataset_id": "evalset_hr_v1"},
    )
    assert response.status_code == 403


def test_create_evaluation_run_conflict():
    headers = get_auth_header()
    payload = {
        "dataset_id": "evalset_hr_v2",
    }

    # Should fail because previous test created a run that is QUEUED
    response = client.post("/api/v1/evaluation/runs", headers=headers, json=payload)
    assert response.status_code == 409
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "EVALUATION_RUN_CONFLICT"


def test_create_evaluation_run_dataset_not_found():
    headers = get_auth_header()

    # Manually set active evaluation runs to COMPLETED to bypass conflict check
    async def set_runs_completed():
        async with TestingSessionLocal() as session:
            await session.execute(
                EvaluationRunDB.__table__.update().values(state="COMPLETED")
            )
            await session.commit()

    import asyncio
    asyncio.run(set_runs_completed())

    payload = {
        "dataset_id": "invalid_dataset_9999",
    }

    response = client.post("/api/v1/evaluation/runs", headers=headers, json=payload)
    assert response.status_code == 404
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "EVALUATION_DATASET_NOT_FOUND"


def test_get_evaluation_run_status_success():
    headers = get_auth_header()

    # Ensure no active runs and create a fresh run
    async def set_runs_completed():
        async with TestingSessionLocal() as session:
            await session.execute(
                EvaluationRunDB.__table__.update().values(state="COMPLETED")
            )
            await session.commit()

    import asyncio
    asyncio.run(set_runs_completed())

    create_payload = {"dataset_id": "evalset_hr_v1"}
    create_res = client.post("/api/v1/evaluation/runs", headers=headers, json=create_payload)
    run_id = create_res.json()["data"]["run_id"]

    response = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["run_id"] == run_id
    assert res["data"]["dataset_id"] == "evalset_hr_v1"
    assert "quality_gate" in res["data"]


def test_get_evaluation_run_status_not_found():
    headers = get_auth_header()
    fake_run_id = str(uuid.uuid4())

    response = client.get(f"/api/v1/evaluation/runs/{fake_run_id}", headers=headers)
    assert response.status_code == 404
    res = response.json()
    assert res["success"] is False
    assert res["error"]["code"] == "EVALUATION_RUN_NOT_FOUND"

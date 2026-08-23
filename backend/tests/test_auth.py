import uuid

import pytest
import pytest_asyncio
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthService

from tests.conftest import TestingSessionLocal, client


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_auth_test_data():
    async with TestingSessionLocal() as session:
        user_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        user = UserDB(
            id=user_id,
            email="employee@company.com",
            hashed_password=hash_password("password123"),
        )
        user.profile = ProfileDB(
            id=user_id,
            display_name="Nguyen Van A",
            role="EMPLOYEE",
            department="Engineering",
        )

        admin = UserDB(
            id=admin_id,
            email="admin@company.com",
            hashed_password=hash_password("admin123"),
        )
        admin.profile = ProfileDB(
            id=admin_id,
            display_name="Tran Thi B (HR)",
            role="HR_ADMIN",
            department="HR",
        )

        session.add_all([user, admin])
        await session.commit()


def test_token_creation_and_decoding():
    payload = {"sub": "user123", "email": "test@example.com"}
    access_tok = create_access_token(payload)
    refresh_tok = create_refresh_token(payload)

    decoded_access = decode_token(access_tok)
    decoded_refresh = decode_token(refresh_tok)

    assert decoded_access["sub"] == "user123"
    assert decoded_access["type"] == "access"

    assert decoded_refresh["sub"] == "user123"
    assert decoded_refresh["type"] == "refresh"


@pytest.mark.asyncio
async def test_auth_service_login_success():
    async with TestingSessionLocal() as session:
        login_req = LoginRequest(email="employee@company.com", password="password123")
        res = await AuthService.login(session, login_req)

        assert res.token_type == "bearer"
        assert res.access_token is not None
        assert res.refresh_token is not None

        decoded_access = decode_token(res.access_token)
        assert decoded_access["email"] == "employee@company.com"
        assert decoded_access["role"] == "EMPLOYEE"
        assert decoded_access["department"] == "Engineering"


@pytest.mark.asyncio
async def test_auth_service_login_invalid_password():
    async with TestingSessionLocal() as session:
        login_req = LoginRequest(email="employee@company.com", password="wrongpassword")
        with pytest.raises(AuthenticationError):
            await AuthService.login(session, login_req)


@pytest.mark.asyncio
async def test_auth_service_refresh_token_success():
    async with TestingSessionLocal() as session:
        login_req = LoginRequest(email="admin@company.com", password="admin123")
        login_res = await AuthService.login(session, login_req)

        refresh_res = await AuthService.refresh_access_token(session, login_res.refresh_token)
        assert refresh_res.access_token is not None
        assert refresh_res.refresh_token is not None

        decoded = decode_token(refresh_res.access_token)
        assert decoded["email"] == "admin@company.com"
        assert decoded["role"] == "HR_ADMIN"


@pytest.mark.asyncio
async def test_auth_service_refresh_token_invalid_type():
    async with TestingSessionLocal() as session:
        login_req = LoginRequest(email="employee@company.com", password="password123")
        login_res = await AuthService.login(session, login_req)

        with pytest.raises(AuthenticationError):
            await AuthService.refresh_access_token(session, login_res.access_token)


def test_api_login_endpoint():
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@company.com", "password": "password123"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "access_token" in res_data["data"]
    assert "refresh_token" in res_data["data"]
    assert res_data["data"]["token_type"] == "bearer"


def test_api_refresh_endpoint():
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@company.com", "password": "password123"},
    )
    refresh_token = login_resp.json()["data"]["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "access_token" in res_data["data"]
    assert "refresh_token" in res_data["data"]


def test_api_me_endpoint_success():
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@company.com", "password": "admin123"},
    )
    access_token = login_resp.json()["data"]["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["email"] == "admin@company.com"
    assert res_data["data"]["role"] == "HR_ADMIN"
    assert res_data["data"]["department"] == "HR"


def test_api_me_endpoint_unauthorized():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_api_register_endpoint_success():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@company.com",
            "password": "securepassword123",
            "department": "Marketing",
            "full_name": "Nguyen Van C",
        },
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["email"] == "newuser@company.com"
    assert res_data["data"]["role"] == "EMPLOYEE"
    assert res_data["data"]["department"] == "Marketing"


def test_api_register_endpoint_duplicate_email():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "employee@company.com",
            "password": "password123",
            "department": "Engineering",
        },
    )
    assert response.status_code == 400


def test_api_register_endpoint_validation_error():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid@company.com",
            "password": "123",
            "department": "Engineering",
        },
    )
    assert response.status_code == 422


def test_api_register_rejects_noncanonical_department():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong-department@company.com",
            "password": "password123",
            "department": "hr ",
        },
    )
    assert response.status_code == 422


def test_api_register_cannot_self_assign_admin_role():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "role-escalation@company.com",
            "password": "password123",
            "department": "HR",
            "role": "SUPER_ADMIN",
        },
    )
    assert response.status_code == 422


def test_api_register_accepts_department_user_role():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "dept-user@company.com",
            "password": "password123",
            "department": "Engineering",
            "role": "department_user",
        },
    )
    assert response.status_code == 201
    assert response.json()["data"]["role"] == "DEPARTMENT_USER"


def test_api_register_defaults_to_employee_without_role():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "default-role@company.com",
            "password": "password123",
            "department": "Finance",
        },
    )
    assert response.status_code == 201
    assert response.json()["data"]["role"] == "EMPLOYEE"


def test_api_register_rejects_hr_admin_role():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "hr-admin-escalation@company.com",
            "password": "password123",
            "department": "HR",
            "role": "hr_admin",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ROLE_NOT_ALLOWED_FOR_SIGNUP"

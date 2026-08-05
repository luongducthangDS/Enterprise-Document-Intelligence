import uuid

import pytest
import pytest_asyncio
from app.api.dependencies.db_deps import get_db
from app.core.config import get_settings
from app.core.database import Base
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password
from app.domain.models.user import UserDB
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthService
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from main import app

settings = get_settings()

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        user = UserDB(
            id=uuid.uuid4(),
            email="employee@company.com",
            hashed_password=hash_password("password123"),
            full_name="Nguyen Van A",
            role="EMPLOYEE",
            department="Engineering",
        )
        admin = UserDB(
            id=uuid.uuid4(),
            email="admin@company.com",
            hashed_password=hash_password("admin123"),
            full_name="Tran Thi B (HR)",
            role="HR_ADMIN",
            department="HR",
        )
        session.add_all([user, admin])
        await session.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


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
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_api_refresh_endpoint():
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@company.com", "password": "password123"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_api_me_endpoint_success():
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@company.com", "password": "admin123"},
    )
    access_token = login_resp.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@company.com"
    assert data["role"] == "HR_ADMIN"
    assert data["department"] == "HR"


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
    data = response.json()
    assert data["email"] == "newuser@company.com"
    assert data["role"] == "EMPLOYEE"
    assert data["department"] == "Marketing"


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

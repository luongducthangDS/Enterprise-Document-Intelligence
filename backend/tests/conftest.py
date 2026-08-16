import os

import pytest_asyncio
from app.api.dependencies.db_deps import get_db
from app.core.database import AsyncSessionLocal, Base
from app.schemas.agent import AgentAnswerDTO
from app.services.chat_service import ChatService
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from main import app

TEST_DB_FILE = "./test_temp.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 60},
    pool_size=50,
    max_overflow=50,
)


@event.listens_for(test_engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


TestingSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


class FakeAgentClient:
    async def query_agent(
        self,
        user_id: str,
        query: str,
        department: str,
        request_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentAnswerDTO:
        normalized_query = query.lower()
        if "khong co trong tai lieu" in normalized_query or "không có trong tài liệu" in normalized_query:
            return AgentAnswerDTO(
                response="Toi chua tim thay du thong tin trong tai lieu hien co.",
                intent="hr_question",
                confidence_score=0.0,
                escalate=True,
                escalate_reason="low_confidence",
                ticket_draft={
                    "employee_question": query,
                    "escalate_reason": "low_confidence",
                    "confidence_score": 0.0,
                    "category": "GENERAL",
                    "target_department": "HRBP",
                    "priority": "Medium",
                },
            )
        return AgentAnswerDTO(
            response=f"Agent answer for {department}: {query}",
            intent="hr_question",
            confidence_score=0.9,
            citations=[
                {
                    "chunk_id": "policy::0001",
                    "source_file": "policy.pdf",
                    "title": "HR Policy",
                    "page_start": 3,
                    "page_end": 3,
                    "category": "GENERAL",
                    "is_official_policy": True,
                }
            ],
        )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database():
    ChatService.session_factory = TestingSessionLocal
    original_agent_client = ChatService.agent_client
    original_background_tasks_enabled = ChatService.background_tasks_enabled
    ChatService.agent_client = FakeAgentClient()
    ChatService.background_tasks_enabled = False

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.clear()
    ChatService.session_factory = AsyncSessionLocal
    ChatService.agent_client = original_agent_client
    ChatService.background_tasks_enabled = original_background_tasks_enabled
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


@pytest_asyncio.fixture
async def db_session():
    async with TestingSessionLocal() as session:
        yield session


client = TestClient(app)

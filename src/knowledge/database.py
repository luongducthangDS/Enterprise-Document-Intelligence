"""Database Connection & Session Management for Knowledge Layer.

Hỗ trợ:
1. SQLite local (`data/knowledge.db`) với chế độ WAL và Foreign Key Enforcement (`PRAGMA foreign_keys = ON`).
2. Tương thích hoàn toàn với PostgreSQL / Supabase khi chuyển lên cloud.
"""
from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.knowledge.models import Base

DEFAULT_DB_PATH = "data/knowledge.db"


def get_database_url(db_path: str = DEFAULT_DB_PATH) -> str:
    """Trả về database URI chuẩn."""
    custom_url = os.getenv("KNOWLEDGE_DATABASE_URL")
    if custom_url:
        return custom_url

    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    # 4 slashes on Windows for absolute path or relative
    return f"sqlite:///{db_path}"


def create_knowledge_engine(db_url: str | None = None) -> Engine:
    """Tạo SQLAlchemy Engine có kích hoạt foreign keys cho SQLite."""
    url = db_url or get_database_url()
    is_sqlite = url.startswith("sqlite")

    engine = create_engine(
        url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


_global_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def init_db(engine: Engine | None = None, db_url: str | None = None) -> Engine:
    """Khởi tạo toàn bộ 7 bảng trong Database."""
    global _global_engine, _SessionFactory
    if engine is None:
        engine = create_knowledge_engine(db_url)

    _global_engine = engine
    _SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    Base.metadata.create_all(bind=engine)
    return engine


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    """Context manager cung cấp Database Session an toàn."""
    global _SessionFactory, _global_engine
    if _SessionFactory is None or (engine is not None and engine != _global_engine):
        eng = engine or _global_engine or create_knowledge_engine()
        init_db(eng)

    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

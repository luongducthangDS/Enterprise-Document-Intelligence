"""Database Connection & Session Management for Knowledge Layer.

Kết nối tới Supabase PostgreSQL Cloud (production).
Thứ tự ưu tiên URL:
  1. Env var KNOWLEDGE_DATABASE_URL (nếu muốn tách riêng DB tri thức)
  2. Env var DATABASE_URL (chung với backend — Supabase PostgreSQL)
  3. SQLite local fallback (chỉ dùng cho pytest in-memory isolation)
"""
from __future__ import annotations

import os
import warnings
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Load .env tự động nếu các biến chưa được set — ưu tiên system env đã được set bởi process.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # override=False: giữ system env nếu đã có
except ImportError:
    pass  # dotenv không bắt buộc trong môi trường container

from src.knowledge.models import Base, apply_schema

_SQLITE_FALLBACK = "sqlite:///:memory:"


def get_database_url() -> str:
    """Trả về database URL theo thứ tự ưu tiên:
    KNOWLEDGE_DATABASE_URL → DATABASE_URL → SQLite in-memory (test-only fallback).
    """
    # 1. Knowledge-layer dedicated URL (optional override)
    custom_url = os.getenv("KNOWLEDGE_DATABASE_URL", "").strip()
    if custom_url:
        return _normalise_postgres_url(custom_url)

    # 2. Shared Supabase PostgreSQL URL (set bởi .env)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return _normalise_postgres_url(database_url)

    # 3. Fallback: SQLite in-memory chỉ dùng trong pytest
    import warnings
    warnings.warn(
        "[Knowledge DB] Không tìm thấy DATABASE_URL — dùng SQLite in-memory (test-only). "
        "Hãy set biến môi trường DATABASE_URL hoặc KNOWLEDGE_DATABASE_URL cho production.",
        stacklevel=2,
    )
    return _SQLITE_FALLBACK


def _normalise_postgres_url(url: str) -> str:
    """Đảm bảo URL dùng driver psycopg2 (sync) phù hợp với SQLAlchemy sync engine."""
    # asyncpg driver không tương thích với sync SQLAlchemy create_engine
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and "+" not in url.split("://")[0]:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def create_knowledge_engine(db_url: str | None = None) -> Engine:
    """Tạo SQLAlchemy Engine. PostgreSQL cho production, SQLite chỉ cho pytest."""
    url = db_url or get_database_url()
    is_sqlite = url.startswith("sqlite")

    kwargs: dict = {
        "echo": False,
        "future": True,
    }
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool
            kwargs["poolclass"] = StaticPool
    else:
        # Connection pool phù hợp với Supabase Transaction Pooler (port 6543)
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 3
        kwargs["max_overflow"] = 2
        kwargs["pool_recycle"] = 300
        kwargs["connect_args"] = {"options": "-csearch_path=knowledge,public"}

    engine = create_engine(url, **kwargs)

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
    """Khởi tạo toàn bộ bảng trong Database (create_all idempotent).
    
    Với PostgreSQL/Supabase: tự động tạo schema 'knowledge' nếu chưa tồn tại
    để tách biệt hoàn toàn với schema 'public' của backend.
    """
    global _global_engine, _SessionFactory
    if engine is None:
        engine = create_knowledge_engine(db_url)

    _global_engine = engine
    _SessionFactory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    # PostgreSQL: tạo schema 'knowledge' và áp dụng cho tất cả tables
    if not engine.url.drivername.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS knowledge"))
            conn.commit()
        apply_schema("knowledge")
    else:
        apply_schema(None)
    Base.metadata.create_all(bind=engine)
    return engine


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    """Context manager cung cấp Database Session an toàn (commit on success, rollback on error)."""
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


def create_all_tables(engine: Engine) -> None:
    """Tạo tất cả bảng Knowledge Layer — dùng cho init và pytest setUp."""
    init_db(engine)


def drop_all_tables(engine: Engine) -> None:
    """Xóa tất cả bảng Knowledge Layer — dùng cho pytest tearDown."""
    if engine.url.drivername.startswith("sqlite"):
        apply_schema(None)
    Base.metadata.drop_all(bind=engine)

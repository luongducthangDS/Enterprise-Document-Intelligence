"""Database Engine & Session Management for Knowledge Layer inside Backend."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models.knowledge import KnowledgeBase, apply_knowledge_schema


def get_knowledge_database_url() -> str:
    url = os.environ.get("KNOWLEDGE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///:memory:"

    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return url


def create_knowledge_engine(db_url: str | None = None) -> Engine:
    url = db_url or get_knowledge_database_url()
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


def init_knowledge_db(engine: Engine | None = None, db_url: str | None = None) -> Engine:
    global _global_engine, _SessionFactory
    if engine is None:
        engine = create_knowledge_engine(db_url)

    _global_engine = engine
    _SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    if engine.url.drivername.startswith("sqlite"):
        apply_knowledge_schema(None)
        KnowledgeBase.metadata.create_all(bind=engine)
    else:
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS knowledge"))
            conn.commit()
        apply_knowledge_schema("knowledge")
        KnowledgeBase.metadata.create_all(bind=engine)

    return engine


@contextmanager
def get_knowledge_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    global _global_engine, _SessionFactory
    if _SessionFactory is None or (engine is not None and engine is not _global_engine):
        init_knowledge_db(engine=engine)

    assert _SessionFactory is not None
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
    init_knowledge_db(engine=engine)


def drop_all_tables(engine: Engine) -> None:
    if engine.url.drivername.startswith("sqlite"):
        apply_knowledge_schema(None)
    else:
        apply_knowledge_schema("knowledge")
    KnowledgeBase.metadata.drop_all(bind=engine)

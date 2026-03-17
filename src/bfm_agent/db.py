from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from bfm_agent.config import get_settings
from bfm_agent.models import AppConfig, Base


SCHEMA_VERSION = "2026-03-17-five-agent-v1"


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def _drop_all_tables() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name in inspector.get_table_names():
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}"')


def reset_schema() -> None:
    _drop_all_tables()
    Base.metadata.create_all(bind=get_engine())
    with session_scope() as session:
        session.merge(AppConfig(key="schema_version", value=SCHEMA_VERSION))


def ensure_schema() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    required_tables = set(Base.metadata.tables)
    if not required_tables.issubset(table_names):
        reset_schema()
        return

    try:
        with session_scope() as session:
            schema_version = session.scalar(select(AppConfig.value).where(AppConfig.key == "schema_version"))
            if schema_version != SCHEMA_VERSION:
                raise RuntimeError("Schema version mismatch")
    except Exception:
        reset_schema()


def init_db() -> None:
    ensure_schema()


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

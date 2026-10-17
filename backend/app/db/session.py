"""Engine and session factory."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


def make_engine(url: str, pool_size: int = 5, max_overflow: int = 1) -> Engine:
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    # ISSUE-012: the pool was 10 + 10 per worker (40 across 2 workers), but the Supabase Free
    # session pooler admits 15 clients, so under 20 users connections were refused
    # (EMAXCONNSESSION) and requests failed with 500s. The pool is now sized from settings to
    # fit the pooler; when it's busy, a request waits for a connection instead of failing.
    return create_engine(
        url, pool_size=pool_size, max_overflow=max_overflow, pool_timeout=20, pool_pre_ping=True
    )


@lru_cache
def get_engine() -> Engine:
    from app import faults

    settings = get_settings()
    engine = make_engine(
        settings.server_database_url, settings.db_pool_size, settings.db_max_overflow
    )
    faults.slow_down(engine, faults.active(settings), settings.fault_db_delay_ms)
    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()

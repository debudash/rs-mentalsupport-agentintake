"""Engine and session factory."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

# Safe on the transaction pooler, the session pooler and plain Postgres alike.
POSTGRES_CONNECT_ARGS = {"prepare_threshold": None}


def make_engine(
    url: str, pool_size: int = 4, max_overflow: int = 1, pool_timeout: float = 20
) -> Engine:
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    # ISSUE-012: the pool was 10 + 10 per worker (40 across 2 workers), but the Supabase Free
    # session pooler admits 15 clients, so under 20 users connections were refused
    # (EMAXCONNSESSION) and requests failed with 500s. The pool is now sized from settings to
    # fit the pooler; when it's busy, a request waits for a connection instead of failing.
    # Continued: in session mode every client connection pins one of the pooler's 15 server
    # slots, idle or orphaned by a killed container, so the app uses the transaction pooler
    # (port 6543), which holds a slot only during a transaction. It can't keep prepared
    # statements across transactions, so psycopg must never prepare them.
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=True,
        connect_args=POSTGRES_CONNECT_ARGS,
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


# ISSUE-013: the timing middleware saved each request's timing record from the request pool
# while the request's own session still held a connection (read-only requests never commit).
# With a small pool, a handful of such requests each held one connection and waited for a
# second: a deadlock until the pool timeout. Timing records get their own one-connection
# pool, which never waits on the request pool, so the cycle can't form. A busy telemetry
# pool makes a record wait at most 2 s, then it's dropped - telemetry never fails a request.
@lru_cache
def get_telemetry_engine() -> Engine:
    settings = get_settings()
    if settings.server_database_url.startswith("sqlite"):
        return get_engine()  # one in-process database; tests read the records back
    return make_engine(settings.server_database_url, 1, 0, pool_timeout=2)


@lru_cache
def get_telemetry_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_telemetry_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()

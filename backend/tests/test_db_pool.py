"""The app's database connections must fit the Supabase pooler it connects through."""

import pytest

from app.config import Settings
from app.db.session import make_engine

SUPABASE_FREE_SESSION_POOLER_CLIENTS = 15
WORKERS = 2  # Dockerfile: --workers ${WEB_CONCURRENCY:-2}
HEADROOM = 3  # migrations at start-up, the seed, an operator's query


# ISSUE-012 — found by k6 against the deployed app: 11% of requests failed with
# EMAXCONNSESSION once 20 users were active.
def test_postgres_pool_fits_the_supabase_session_pooler():
    settings = Settings(_env_file=None)
    engine = make_engine(
        "postgresql+psycopg://user:pw@localhost:5432/db",
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    timing_records = 1  # its own pool (ISSUE-013)
    per_worker = engine.pool.size() + engine.pool._max_overflow + timing_records
    assert per_worker * WORKERS <= SUPABASE_FREE_SESSION_POOLER_CLIENTS - HEADROOM


def test_pool_size_is_configurable_for_bigger_poolers():
    engine = make_engine("postgresql+psycopg://user:pw@localhost:5432/db", 20, 5)
    assert (engine.pool.size(), engine.pool._max_overflow) == (20, 5)


# ISSUE-012 (continued): even a pool that fits got refused after a redeploy, because in
# session mode every client connection - idle, or left behind by a killed container - pins
# one of the 15 server slots. The app uses the transaction pooler (port 6543), which only
# holds a slot during a transaction and doesn't support prepared statements.
def test_postgres_connections_never_use_prepared_statements():
    from sqlalchemy import event

    engine = make_engine("postgresql+psycopg://user:pw@localhost:6543/db")
    seen = {}

    @event.listens_for(engine, "do_connect")
    def capture(dialect, conn_rec, cargs, cparams):
        seen.update(cparams)
        raise RuntimeError("stop before the network")

    with pytest.raises(Exception, match="stop before the network"):
        engine.connect()
    assert "prepare_threshold" in seen and seen["prepare_threshold"] is None


# ISSUE-013 — found by k6 against the deployed app once the pool was small (ISSUE-012):
# non-chat requests waited the full 20 s pool timeout, then failed.
def test_timing_record_is_saved_while_requests_hold_every_pooled_connection(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool

    from app import main
    from app.db import session as db_session
    from app.db.models import Base, TimingRecord

    url = f"sqlite:///{tmp_path / 'pool.db'}"
    request_pool = create_engine(
        url, poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=0.5
    )
    Base.metadata.create_all(request_pool)
    # Before the fix main used the request pool for timing records; it no longer imports it.
    monkeypatch.setattr(
        main, "get_sessionmaker", lambda: sessionmaker(bind=request_pool), raising=False
    )
    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: sessionmaker(bind=request_pool))
    telemetry_pool = create_engine(url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    monkeypatch.setattr(
        db_session,
        "get_telemetry_sessionmaker",
        lambda: sessionmaker(bind=telemetry_pool),
    )

    held = request_pool.connect()  # a read-only request still holding its connection
    held.execute(text("select 1"))
    try:
        main._save_timing(TimingRecord(endpoint="GET /api/me", status_code=200, total_ms=5.0))
    finally:
        held.close()
    with telemetry_pool.connect() as conn:
        assert conn.execute(text("select count(*) from timing_records")).scalar() == 1

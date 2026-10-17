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
    per_worker = engine.pool.size() + engine.pool._max_overflow
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

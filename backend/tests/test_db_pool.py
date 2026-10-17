"""The app's database connections must fit the Supabase pooler it connects through."""

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

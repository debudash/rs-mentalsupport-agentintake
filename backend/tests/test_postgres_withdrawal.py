"""Integration tests that need real Supabase Postgres (the auth schema).

Run with TEST_POSTGRES_URL pointing at a local Supabase database, e.g.
  TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres pytest -m postgres
Skipped otherwise.
"""

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.consent import _delete_auth_audit_rows

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL not set")]

SYSTEM_ACTOR = "00000000-0000-0000-0000-000000000000"


def audit_row(
    session: Session, user_id: str, actor_id: str = SYSTEM_ACTOR, action: str = "user_signedup"
):
    payload = {
        "action": action,
        "actor_id": actor_id,
        "actor_username": "service_role",
        "traits": {
            "user_id": user_id,
            "user_email": f"{user_id[:6]}@riverside.test",
            "provider": "email",
        },
    }
    session.execute(
        text(
            "insert into auth.audit_log_entries (instance_id, id, payload, created_at, ip_address) "
            "values (:inst, :id, cast(:payload as json), now(), '203.0.113.7')"
        ),
        {"inst": SYSTEM_ACTOR, "id": str(uuid.uuid4()), "payload": json.dumps(payload)},
    )


def rows_for(session: Session, user_id: str) -> int:
    return session.execute(
        text(
            "select count(*) from auth.audit_log_entries where payload->>'actor_id' = :id "
            "or payload->'traits'->>'user_id' = :id"
        ),
        {"id": user_id},
    ).scalar()


def _has_supabase_auth(engine) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("select to_regclass('auth.audit_log_entries')")).scalar())


def test_withdrawal_removes_audit_rows_that_name_the_user_in_traits():
    """ISSUE-001 regression. Found by: verifying Withdrawal against local Supabase — sign-up
    and deletion events (with email and IP) survived because they carry the user in
    traits.user_id, with the system as actor."""
    engine = create_engine(URL)
    if not _has_supabase_auth(engine):
        pytest.skip("needs Supabase's auth schema (plain Postgres in CI has none)")
    gone, kept = str(uuid.uuid4()), str(uuid.uuid4())
    with Session(engine) as session:
        audit_row(session, gone)  # sign-up by the system/admin
        audit_row(session, gone, action="user_deleted")
        audit_row(session, gone, actor_id=gone, action="login")  # self-initiated event
        audit_row(session, kept)
        session.commit()

        assert _delete_auth_audit_rows(session, gone) is True
        session.commit()

        assert rows_for(session, gone) == 0
        assert rows_for(session, kept) == 1
        session.execute(
            text("delete from auth.audit_log_entries where payload->'traits'->>'user_id' = :id"),
            {"id": kept},
        )
        session.commit()

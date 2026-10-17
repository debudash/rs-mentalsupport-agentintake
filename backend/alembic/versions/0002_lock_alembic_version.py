"""Lock alembic's own bookkeeping table from the browser-facing roles too.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("alter table public.alembic_version enable row level security")
        # Supabase's browser roles; absent on plain Postgres (e.g. CI), so revoke only if present.
        op.execute(
            "do $$ begin if exists (select 1 from pg_roles where rolname = 'anon') then "
            "execute 'revoke all on public.alembic_version from anon, authenticated'; end if; end $$"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("alter table public.alembic_version disable row level security")

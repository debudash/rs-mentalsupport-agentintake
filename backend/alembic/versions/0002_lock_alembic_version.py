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
        op.execute("revoke all on public.alembic_version from anon, authenticated")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("alter table public.alembic_version disable row level security")

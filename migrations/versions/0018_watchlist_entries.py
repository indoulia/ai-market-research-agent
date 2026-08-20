"""add watchlist_entries table

Revision ID: 0018_watchlist_entries
Revises: 0017_discovery_segments

EPIC-M1.18: a deterministic, append-only intake boundary for stocks a user (or
other source) wants monitored -- one row per ACTIVATE/DEACTIVATE event rather than
a mutable boolean, so watchlist history is preserved rather than silently
overwritten, and current active/inactive state is derived from the latest event.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_watchlist_entries"
down_revision = "0017_discovery_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_watchlist_entries_stock_id", "watchlist_entries", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_entries_stock_id", table_name="watchlist_entries")
    op.drop_table("watchlist_entries")

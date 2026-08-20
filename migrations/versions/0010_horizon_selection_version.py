"""add horizon_selection_version to predictions

Revision ID: 0010_horizon_selection_version
Revises: 0009_watchlist_evaluations

EPIC-M1.10: persists which versioned horizon-selection rule (app/horizon.py
SELECTION_VERSION) chose this recommendation's horizon_days, so the decision stays
traceable even as the selection rule evolves.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_horizon_selection_version"
down_revision = "0009_watchlist_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("horizon_selection_version", sa.String(32), nullable=False, server_default="UNVERSIONED"),
    )
    op.alter_column("predictions", "horizon_selection_version", server_default=None)


def downgrade() -> None:
    op.drop_column("predictions", "horizon_selection_version")

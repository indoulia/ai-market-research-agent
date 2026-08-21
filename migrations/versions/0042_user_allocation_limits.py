"""add user_allocation_limits table

Revision ID: 0042_user_allocation_limits
Revises: 0041_user_holdings

EPIC-M1.60: versioned, append-only user allocation/risk limits -- the same
"a user can change preferences without mutating history" pattern M1.46
already established for `UserPreference`. The most recent row for a
`user_id` is that user's current effective limit.
"""
from alembic import op
import sqlalchemy as sa

revision = "0042_user_allocation_limits"
down_revision = "0041_user_holdings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_allocation_limits",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("max_position_percentage", sa.Numeric(6, 4), nullable=False),
        sa.Column("max_sector_percentage", sa.Numeric(6, 4), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_allocation_limits_user_id", "user_allocation_limits", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_allocation_limits_user_id", table_name="user_allocation_limits")
    op.drop_table("user_allocation_limits")

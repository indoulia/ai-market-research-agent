"""add multi_horizon_resolutions table

Revision ID: 0043_multi_horizon_resolution
Revises: 0042_user_allocation_limits

EPIC-M1.61: resolve conflicting short/medium/long-horizon views for one
stock into a single, deterministic, immutable presentation decision per
user -- never mutated, only superseded by a later resolution as new
predictions arrive.
"""
from alembic import op
import sqlalchemy as sa

revision = "0043_multi_horizon_resolution"
down_revision = "0042_user_allocation_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "multi_horizon_resolutions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("primary_prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("primary_horizon_days", sa.Integer(), nullable=False),
        sa.Column("conflicting_prediction_ids", sa.JSON(), nullable=False),
        sa.Column("has_conflict", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_multi_horizon_resolutions_stock_id", "multi_horizon_resolutions", ["stock_id"])
    op.create_index("ix_multi_horizon_resolutions_user_id", "multi_horizon_resolutions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_multi_horizon_resolutions_user_id", table_name="multi_horizon_resolutions")
    op.drop_index("ix_multi_horizon_resolutions_stock_id", table_name="multi_horizon_resolutions")
    op.drop_table("multi_horizon_resolutions")

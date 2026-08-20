"""add recommendation_observations table

Revision ID: 0025_recommendation_observations
Revises: 0024_data_fetch_attempts

EPIC-M1.36: tracks every issued recommendation from issuance through its
selected horizon via one immutable daily observation row per trading day,
never overwriting a prior day's observation once recorded.
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_recommendation_observations"
down_revision = "0024_data_fetch_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("observation_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("close_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("return_since_entry", sa.Numeric(10, 6), nullable=True),
        sa.Column("data_available", sa.Boolean(), nullable=False),
        sa.Column("horizon_complete", sa.Boolean(), nullable=False),
        sa.Column("observation_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "day_number", name="uq_observation_prediction_day"),
    )
    op.create_index("ix_recommendation_observations_prediction_id", "recommendation_observations", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_observations_prediction_id", table_name="recommendation_observations")
    op.drop_table("recommendation_observations")

"""add recommendation_revalidation_outcomes table

Revision ID: 0044_recommendation_reval
Revises: 0043_multi_horizon_resolution

EPIC-M1.62: automatically determine whether an active recommendation
remains valid, producing an explicit UNCHANGED/UPDATED/WITHDRAWN/EXPIRED
outcome. Immutable, idempotent per (prediction_id, checked_at) -- never
mutates the underlying Prediction or any prior revalidation outcome.
"""
from alembic import op
import sqlalchemy as sa

revision = "0044_recommendation_reval"
down_revision = "0043_multi_horizon_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_revalidation_outcomes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=False),
        sa.Column("elapsed_days", sa.Integer(), nullable=False),
        sa.Column("current_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("evidence_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revalidation_engine_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "checked_at", name="uq_revalidation_prediction_checked_at"),
    )
    op.create_index("ix_recommendation_revalidation_outcomes_prediction_id", "recommendation_revalidation_outcomes", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_revalidation_outcomes_prediction_id", table_name="recommendation_revalidation_outcomes")
    op.drop_table("recommendation_revalidation_outcomes")

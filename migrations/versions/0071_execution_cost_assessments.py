"""add execution_cost_assessments table

Revision ID: 0071_execution_cost
Revises: 0070_bias_guard

EPIC-M1.98: measure prediction usefulness on a realistic, cost-adjusted
net basis alongside the existing gross outcome, without ever mutating
the immutable gross PredictionOutcome itself.
"""
from alembic import op
import sqlalchemy as sa

revision = "0071_execution_cost"
down_revision = "0070_bias_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_cost_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("gross_return", sa.Numeric(10, 6), nullable=False),
        sa.Column("liquidity_bucket", sa.String(length=32), nullable=False),
        sa.Column("executability_verdict", sa.String(length=32), nullable=False),
        sa.Column("estimated_cost_percent", sa.Numeric(10, 6), nullable=True),
        sa.Column("net_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("cost_model_version", sa.String(length=32), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", name="uq_execution_cost_prediction"),
    )


def downgrade() -> None:
    op.drop_table("execution_cost_assessments")

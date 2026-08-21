"""add positive_opportunity_rankings table

Revision ID: 0072_opportunity_rank
Revises: 0071_execution_cost

EPIC-M1.87: rank positive-gated candidates by expected return, probability,
trust, reward/risk, evidence quality and stability, preserving a full,
reconstructable snapshot of every ranking decision.
"""
from alembic import op
import sqlalchemy as sa

revision = "0072_opportunity_rank"
down_revision = "0071_execution_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positive_opportunity_rankings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("composite_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("expected_return_component", sa.Numeric(10, 6), nullable=True),
        sa.Column("probability_component", sa.Numeric(10, 6), nullable=True),
        sa.Column("trust_component", sa.Numeric(10, 6), nullable=True),
        sa.Column("reward_risk_component", sa.Numeric(10, 6), nullable=True),
        sa.Column("evidence_quality_component", sa.Numeric(10, 6), nullable=True),
        sa.Column("stability_component", sa.Numeric(10, 6), nullable=True),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ranking_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_opportunity_ranking_prediction_evaluated_at"),
    )


def downgrade() -> None:
    op.drop_table("positive_opportunity_rankings")

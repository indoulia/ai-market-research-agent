"""add position_risk_assessments table

Revision ID: 0040_position_risk_assessment
Revises: 0039_learning_pipeline_gate

EPIC-M1.58: quantify recommendation-level downside, reward/risk, and
volatility-adjusted risk from M1.47's already-published target/stop-loss,
plus a horizon-consistency check against the underlying ATR%. One
immutable, versioned row per (prediction_id, assessment_rule_version).
"""
from alembic import op
import sqlalchemy as sa

revision = "0040_position_risk_assessment"
down_revision = "0039_learning_pipeline_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_risk_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("recommendation_publication_id", sa.BigInteger(), sa.ForeignKey("recommendation_publications.id"), nullable=False),
        sa.Column("risk_percentage", sa.Numeric(10, 6), nullable=False),
        sa.Column("reward_percentage", sa.Numeric(10, 6), nullable=False),
        sa.Column("reward_risk_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("atr_percent", sa.Numeric(12, 6), nullable=False),
        sa.Column("risk_in_atr_units", sa.Numeric(10, 4), nullable=False),
        sa.Column("reward_in_atr_units", sa.Numeric(10, 4), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("horizon_consistent", sa.Boolean(), nullable=False),
        sa.Column("inconsistency_reason", sa.String(length=64), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "assessment_rule_version", name="uq_position_risk_prediction_version"),
    )
    op.create_index("ix_position_risk_assessments_prediction_id", "position_risk_assessments", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_position_risk_assessments_prediction_id", table_name="position_risk_assessments")
    op.drop_table("position_risk_assessments")

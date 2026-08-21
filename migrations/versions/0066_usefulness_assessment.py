"""add prediction_usefulness_assessments and horizon_usefulness_reports tables

Revision ID: 0066_usefulness_assessment
Revises: 0065_attribution_snapshot

EPIC-M1.86: distinguishes directional correctness (M1.5's SUCCESS/
FAILURE) from investment usefulness (a risk-adjusted return-vs-drawdown
ratio) per prediction, plus an aggregate risk-adjusted usefulness report
per (model_version, horizon_days).
"""
from alembic import op
import sqlalchemy as sa

revision = "0066_usefulness_assessment"
down_revision = "0065_attribution_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_usefulness_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("directional_outcome", sa.String(length=32), nullable=False),
        sa.Column("risk_adjusted_ratio", sa.Numeric(12, 6), nullable=True),
        sa.Column("usefulness_verdict", sa.String(length=32), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usefulness_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", name="uq_usefulness_assessment_prediction"),
    )

    op.create_table(
        "horizon_usefulness_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("avg_risk_adjusted_ratio", sa.Numeric(12, 6), nullable=True),
        sa.Column("useful_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_horizon_usefulness_reports_model_version", "horizon_usefulness_reports", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_horizon_usefulness_reports_model_version", table_name="horizon_usefulness_reports")
    op.drop_table("horizon_usefulness_reports")
    op.drop_table("prediction_usefulness_assessments")

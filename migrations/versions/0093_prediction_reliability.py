"""add prediction_reliability_assessments table

Revision ID: 0093_prediction_reliability
Revises: 0092_reproducibility_audit

EPIC-M1.122: attach a confidence interval, evidence-strength indicator
and uncertainty-source read to each prediction's segment-calibration
sample, so a small-sample high-success history cannot look as reliable
as a large-sample one.
"""
from alembic import op
import sqlalchemy as sa

revision = "0093_prediction_reliability"
down_revision = "0092_reproducibility_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_reliability_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("resolved_segment_level", sa.String(length=32), nullable=False),
        sa.Column("resolved_sample_count", sa.Integer(), nullable=False),
        sa.Column("observed_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("confidence_interval_lower", sa.Numeric(10, 6), nullable=True),
        sa.Column("confidence_interval_upper", sa.Numeric(10, 6), nullable=True),
        sa.Column("confidence_interval_half_width", sa.Numeric(10, 6), nullable=True),
        sa.Column("evidence_strength", sa.String(length=32), nullable=False),
        sa.Column("uncertainty_source", sa.String(length=32), nullable=True),
        sa.Column("data_uncertain", sa.Boolean(), nullable=False),
        sa.Column("reliable", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "assessed_at", name="uq_prediction_reliability_prediction_assessed_at"),
    )
    op.create_index("ix_prediction_reliability_assessments_prediction_id", "prediction_reliability_assessments", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_prediction_reliability_assessments_prediction_id", table_name="prediction_reliability_assessments")
    op.drop_table("prediction_reliability_assessments")

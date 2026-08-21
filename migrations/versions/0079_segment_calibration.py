"""add segment_calibration_assessments table

Revision ID: 0079_segment_calibration
Revises: 0078_provider_consensus

EPIC-M1.104: calibrate prediction probabilities at stock, setup, sector,
market-cap and horizon segments, with hierarchical fallback to a
broader segment (and ultimately global) when a specific segment's
sample is too sparse to trust.
"""
from alembic import op
import sqlalchemy as sa

revision = "0079_segment_calibration"
down_revision = "0078_provider_consensus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "segment_calibration_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("resolved_segment_level", sa.String(length=32), nullable=False),
        sa.Column("resolved_segment_key", sa.String(length=128), nullable=False),
        sa.Column("resolved_sample_count", sa.Integer(), nullable=False),
        sa.Column("predicted_mean", sa.Numeric(10, 6), nullable=True),
        sa.Column("observed_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("calibration_error", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("fallback_chain", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calibration_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_segment_calibration_prediction_evaluated_at"),
    )
    op.create_index("ix_segment_calibration_assessments_prediction_id", "segment_calibration_assessments", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_segment_calibration_assessments_prediction_id", table_name="segment_calibration_assessments")
    op.drop_table("segment_calibration_assessments")

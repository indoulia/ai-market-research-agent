"""add confidence_calibration_records table

Revision ID: 0034_confidence_calibration
Revises: 0033_evidence_items

EPIC-M1.49: calibrate `Prediction.confidence` (distinct from M1.23's
existing `predicted_probability` calibration) against realized outcomes from
a strictly prior training window, storing the raw and calibrated values
separately per prediction so a future methodology change never mutates a
past calibration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_confidence_calibration"
down_revision = "0033_evidence_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "confidence_calibration_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("calibration_version", sa.String(length=32), nullable=False),
        sa.Column("raw_confidence", sa.Numeric(10, 8), nullable=False),
        sa.Column("calibrated_confidence", sa.Numeric(10, 8), nullable=True),
        sa.Column("bucket_lower", sa.Numeric(10, 8), nullable=False),
        sa.Column("bucket_upper", sa.Numeric(10, 8), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("calibration_error", sa.Numeric(10, 8), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("training_window_label", sa.String(length=128), nullable=False),
        sa.Column("calibrated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "calibration_version", name="uq_confidence_calibration_prediction_version"),
    )
    op.create_index("ix_confidence_calibration_records_prediction_id", "confidence_calibration_records", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_confidence_calibration_records_prediction_id", table_name="confidence_calibration_records")
    op.drop_table("confidence_calibration_records")

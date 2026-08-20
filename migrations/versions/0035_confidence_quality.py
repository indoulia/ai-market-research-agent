"""add confidence_quality_classifications table

Revision ID: 0035_confidence_quality
Revises: 0034_confidence_calibration

EPIC-M1.50: tell users how trustworthy a confidence percentage is, combining
M1.49's calibration quality/sample size with M1.35's data freshness -- one
immutable, versioned, per-prediction classification, entirely independent
of the raw confidence value itself.
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_confidence_quality"
down_revision = "0034_confidence_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "confidence_quality_classifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("confidence_calibration_record_id", sa.BigInteger(), sa.ForeignKey("confidence_calibration_records.id"), nullable=False),
        sa.Column("quality", sa.String(length=32), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("calibration_verdict", sa.String(length=32), nullable=False),
        sa.Column("is_data_fresh", sa.Boolean(), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("classification_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "classification_rule_version", name="uq_confidence_quality_prediction_version"),
    )
    op.create_index("ix_confidence_quality_classifications_prediction_id", "confidence_quality_classifications", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_confidence_quality_classifications_prediction_id", table_name="confidence_quality_classifications")
    op.drop_table("confidence_quality_classifications")

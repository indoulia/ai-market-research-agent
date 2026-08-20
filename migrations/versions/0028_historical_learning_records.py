"""add historical_learning_records table

Revision ID: 0028_historical_learning_records
Revises: 0027_outcome_measurements

EPIC-M1.39: an immutable, versioned, point-in-time-safe learning dataset --
one row per prediction per dataset construction version, joining
recommendation-time features to the finalized outcome label plus available
segment context (regime, sector, market-cap, discovery source). Excluded/
incomplete records are recorded explicitly rather than silently omitted.
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_historical_learning_records"
down_revision = "0027_outcome_measurements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "historical_learning_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("dataset_version", sa.String(length=32), nullable=False),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("information_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_probability", sa.Numeric(10, 8), nullable=True),
        sa.Column("opportunity_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("sma20_distance", sa.Numeric(12, 6), nullable=True),
        sa.Column("volume_ratio_20d", sa.Numeric(12, 6), nullable=True),
        sa.Column("atr_percent", sa.Numeric(12, 6), nullable=True),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("market_regime", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("market_cap_bucket", sa.String(length=32), nullable=True),
        sa.Column("discovery_source", sa.String(length=32), nullable=True),
        sa.Column("outcome_classification", sa.String(length=32), nullable=True),
        sa.Column("realized_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("dataset_version", "prediction_id", name="uq_learning_record_version_prediction"),
    )
    op.create_index(
        "ix_historical_learning_records_dataset_version",
        "historical_learning_records",
        ["dataset_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_historical_learning_records_dataset_version", table_name="historical_learning_records")
    op.drop_table("historical_learning_records")

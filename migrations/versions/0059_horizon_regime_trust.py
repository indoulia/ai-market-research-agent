"""add horizon_regime_trusts table

Revision ID: 0059_horizon_regime_trust
Revises: 0058_daily_prediction_snapshot

EPIC-M1.79: trust segmented independently by horizon, by market regime,
and by their combination when sample sizes permit. Append-only check log.
"""
from alembic import op
import sqlalchemy as sa

revision = "0059_horizon_regime_trust"
down_revision = "0058_daily_prediction_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_regime_trusts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("segment_type", sa.String(length=16), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("success_rate_standard_error", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("is_low_trust", sa.Boolean(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trust_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_horizon_regime_trusts_model_version", "horizon_regime_trusts", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_horizon_regime_trusts_model_version", table_name="horizon_regime_trusts")
    op.drop_table("horizon_regime_trusts")

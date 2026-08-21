"""add microstructure_snapshots table

Revision ID: 0106_microstructure_liquidity
Revises: 0105_source_authority

EPIC-M1.128: incorporate liquidity, tradability, spread, volume,
price-band and gap behavior into opportunity quality and realistic
outcome evaluation.

Renumbered twice before merging, no schema change either time: first
from 0104 (chained onto 0103_information_latency) after EPIC-M1.123
independently claimed 0104, then from 0105 after EPIC-M1.127
independently claimed 0105 in the same window.
"""
from alembic import op
import sqlalchemy as sa

revision = "0106_microstructure_liquidity"
down_revision = "0105_source_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "microstructure_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("liquidity_bucket", sa.String(length=32), nullable=False),
        sa.Column("previous_liquidity_bucket", sa.String(length=32), nullable=True),
        sa.Column("liquidity_regime_changed", sa.Boolean(), nullable=False),
        sa.Column("average_daily_turnover", sa.Numeric(20, 2), nullable=True),
        sa.Column("gap_percent", sa.Numeric(10, 6), nullable=True),
        sa.Column("gap_bucket", sa.String(length=32), nullable=False),
        sa.Column("probable_circuit_band_event", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", name="uq_microstructure_snapshot_prediction"),
    )


def downgrade() -> None:
    op.drop_table("microstructure_snapshots")

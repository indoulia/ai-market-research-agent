"""add market_regimes table

Revision ID: 0021_market_regimes
Revises: 0020_replay_runs

EPIC-M1.26: classifies each daily candidate scan's market environment
(trend breadth + volatility) from the same point-in-time-safe ScanCandidate
technical features M1.12 already computes -- one immutable regime row per
scan, so recommendation performance can later be measured by regime.
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_market_regimes"
down_revision = "0020_replay_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_regimes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False, unique=True
        ),
        sa.Column("regime", sa.String(length=32), nullable=False),
        sa.Column("breadth_positive_ratio", sa.Numeric(6, 4), nullable=False),
        sa.Column("average_atr_percent", sa.Numeric(12, 6), nullable=True),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("regime_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("market_regimes")

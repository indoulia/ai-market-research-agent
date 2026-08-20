"""add daily_candidate_scans and scan_candidates tables

Revision ID: 0011_daily_candidate_scan
Revises: 0010_horizon_selection_version

EPIC-M1.12: persists each daily universe scan run (one row per scan_date +
universe_version) and, per scan, one row per evaluated stock recording whether it
was eligible and why it was excluded when it was not.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_daily_candidate_scan"
down_revision = "0010_horizon_selection_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_candidate_scans",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("universe_version", sa.String(length=32), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scan_date", "universe_version", name="uq_scan_date_universe_version"),
    )
    op.create_table(
        "scan_candidates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("predicted_probability", sa.Numeric(10, 8), nullable=True),
        sa.Column("confidence", sa.Numeric(10, 8), nullable=True),
        sa.Column("sma20_distance", sa.Numeric(12, 6), nullable=True),
        sa.Column("volume_ratio_20d", sa.Numeric(12, 6), nullable=True),
        sa.Column("atr_percent", sa.Numeric(12, 6), nullable=True),
        sa.Column("data_quality_passed", sa.Boolean(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("feature_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scan_id", "stock_id", name="uq_scan_candidate_scan_stock"),
    )


def downgrade() -> None:
    op.drop_table("scan_candidates")
    op.drop_table("daily_candidate_scans")

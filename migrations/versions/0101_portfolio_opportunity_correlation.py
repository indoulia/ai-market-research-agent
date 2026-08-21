"""add portfolio_correlation_reports, portfolio_utility_assessments and portfolio_selection_effectiveness_reports tables

Revision ID: 0101_portfolio_correlation
Revises: 0100_merge_0091_0099_heads

EPIC-M1.124: portfolio-aware opportunity utility, correlation and
concentration analysis for a scan's simultaneously active candidates.
"""
from alembic import op
import sqlalchemy as sa

revision = "0101_portfolio_correlation"
down_revision = "0100_merge_0091_0099_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_correlation_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("sector_concentration", sa.JSON(), nullable=False),
        sa.Column("high_correlation_pairs", sa.JSON(), nullable=False),
        sa.Column("near_duplicate_stock_ids", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scan_id", "evaluated_at", name="uq_portfolio_correlation_scan_evaluated_at"),
    )

    op.create_table(
        "portfolio_utility_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("base_utility", sa.Numeric(10, 6), nullable=True),
        sa.Column("concentration_penalty", sa.Numeric(10, 6), nullable=False),
        sa.Column("correlation_penalty", sa.Numeric(10, 6), nullable=False),
        sa.Column("preference_penalty", sa.Numeric(10, 6), nullable=False),
        sa.Column("adjusted_utility", sa.Numeric(10, 6), nullable=True),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("penalty_reasons", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utility_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_portfolio_utility_prediction_evaluated_at"),
    )

    op.create_table(
        "portfolio_selection_effectiveness_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("diversified_sample_count", sa.Integer(), nullable=False),
        sa.Column("diversified_success_count", sa.Integer(), nullable=False),
        sa.Column("diversified_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("raw_sample_count", sa.Integer(), nullable=False),
        sa.Column("raw_success_count", sa.Integer(), nullable=False),
        sa.Column("raw_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("success_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effectiveness_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_selection_effectiveness_reports")
    op.drop_table("portfolio_utility_assessments")
    op.drop_table("portfolio_correlation_reports")

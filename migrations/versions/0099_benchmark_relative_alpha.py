"""add benchmarks, benchmark_daily_prices, benchmark_relative_assessments
and benchmark_performance_reports tables

Revision ID: 0099_benchmark_relative
Revises: 0098_purged_embargo_validation

EPIC-M1.129: determine whether a recommendation creates genuine
stock-specific value relative to its industry, sector and broad-market
benchmarks rather than simply benefiting from a rising market.
"""
from alembic import op
import sqlalchemy as sa

revision = "0099_benchmark_relative"
down_revision = "0098_purged_embargo_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmarks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_benchmarks_code"),
    )
    op.create_index("ix_benchmarks_code", "benchmarks", ["code"])

    op.create_table(
        "benchmark_daily_prices",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("benchmark_id", sa.BigInteger(), sa.ForeignKey("benchmarks.id"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(18, 6), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("benchmark_id", "trade_date", name="uq_benchmark_price_benchmark_date"),
    )
    op.create_index("ix_benchmark_daily_prices_benchmark_id", "benchmark_daily_prices", ["benchmark_id"])

    op.create_table(
        "benchmark_relative_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("benchmark_level", sa.String(length=16), nullable=False),
        sa.Column("benchmark_id", sa.BigInteger(), sa.ForeignKey("benchmarks.id"), nullable=True),
        sa.Column("benchmark_code", sa.String(length=64), nullable=True),
        sa.Column("stock_return_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("benchmark_return_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("relative_alpha", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "prediction_id", "benchmark_level", "evaluated_at", name="uq_benchmark_relative_prediction_level_evaluated_at",
        ),
    )
    op.create_index("ix_benchmark_relative_assessments_prediction_id", "benchmark_relative_assessments", ["prediction_id"])

    op.create_table(
        "benchmark_performance_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("benchmark_relative_environment", sa.String(length=32), nullable=False),
        sa.Column("benchmark_level", sa.String(length=16), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("segment_sample_count", sa.Integer(), nullable=False),
        sa.Column("segment_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("baseline_sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_benchmark_performance_reports_environment", "benchmark_performance_reports", ["benchmark_relative_environment"],
    )


def downgrade() -> None:
    op.drop_index("ix_benchmark_performance_reports_environment", table_name="benchmark_performance_reports")
    op.drop_table("benchmark_performance_reports")
    op.drop_index("ix_benchmark_relative_assessments_prediction_id", table_name="benchmark_relative_assessments")
    op.drop_table("benchmark_relative_assessments")
    op.drop_index("ix_benchmark_daily_prices_benchmark_id", table_name="benchmark_daily_prices")
    op.drop_table("benchmark_daily_prices")
    op.drop_index("ix_benchmarks_code", table_name="benchmarks")
    op.drop_table("benchmarks")

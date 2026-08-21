"""add prediction_quality_benchmark_reports table

Revision ID: 0062_quality_benchmark
Revises: 0061_positive_gate_decision

EPIC-M1.82: measures whether positive recommendations create useful
investment outcomes -- directional accuracy, target/stop rates,
expected-vs-realized return, excursion, time-to-exit, and benchmark-
relative return against any real, already-ingested reference stock --
segmented by horizon/regime/sector/market-cap/discovery-source where
sample sizes permit. Append-only check log.
"""
from alembic import op
import sqlalchemy as sa

revision = "0062_quality_benchmark"
down_revision = "0061_positive_gate_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_quality_benchmark_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("directional_accuracy", sa.Numeric(10, 6), nullable=True),
        sa.Column("target_hit_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("stop_hit_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_expected_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_realized_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_max_favorable_excursion", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_max_adverse_excursion", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_time_to_exit_days", sa.Numeric(10, 4), nullable=True),
        sa.Column("benchmark_stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=True),
        sa.Column("avg_benchmark_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_excess_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("benchmark_coverage_count", sa.Integer(), nullable=False),
        sa.Column("benchmark_verdict", sa.String(length=32), nullable=False),
        sa.Column("segment_breakdown", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("trust_reduction_recommended", sa.Boolean(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("benchmark_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prediction_quality_benchmark_reports_model_version", "prediction_quality_benchmark_reports", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_prediction_quality_benchmark_reports_model_version", table_name="prediction_quality_benchmark_reports")
    op.drop_table("prediction_quality_benchmark_reports")

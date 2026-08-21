"""add information_latency_assessments and latency_degradation_reports tables

Revision ID: 0103_information_latency
Revises: 0102_market_calendar

EPIC-M1.126: information latency & data freshness intelligence --
horizon-adjusted SLA assessment per prediction plus windowed latency
degradation reporting per data type.

Numbered 0103 rather than 0101/0102: by the time this merges, both
EPIC-M1.124's migration (0101) and EPIC-M1.121's migration (0102,
market_calendar) had independently claimed those numbers onto the same
0100 base. Renumbered here -- no schema change.
"""
from alembic import op
import sqlalchemy as sa

revision = "0103_information_latency"
down_revision = "0102_market_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "information_latency_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("sla_multiplier", sa.Numeric(6, 4), nullable=False),
        sa.Column("category_latency_seconds", sa.JSON(), nullable=False),
        sa.Column("sla_violations", sa.JSON(), nullable=False),
        sa.Column("suppress_eligibility", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_information_latency_prediction_evaluated_at"),
    )

    op.create_table(
        "latency_degradation_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("average_latency_seconds", sa.Numeric(14, 3), nullable=True),
        sa.Column("baseline_sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_average_latency_seconds", sa.Numeric(14, 3), nullable=True),
        sa.Column("degradation_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("latency_degradation_reports")
    op.drop_table("information_latency_assessments")

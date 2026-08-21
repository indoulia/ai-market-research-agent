"""add sector_relative_assessments and sector_performance_reports tables

Revision ID: 0084_sector_relative
Revises: 0083_setup_combination

EPIC-M1.109: evaluate stocks relative to their sector peers so positive
opportunities reflect relative strength, not only absolute movement.
"""
from alembic import op
import sqlalchemy as sa

revision = "0084_sector_relative"
down_revision = "0083_setup_combination"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sector_relative_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=False),
        sa.Column("peer_group_size", sa.Integer(), nullable=False),
        sa.Column("peer_stock_ids", sa.JSON(), nullable=False),
        sa.Column("target_momentum", sa.Numeric(12, 6), nullable=True),
        sa.Column("peer_mean_momentum", sa.Numeric(12, 6), nullable=True),
        sa.Column("peer_momentum_stdev", sa.Numeric(12, 6), nullable=True),
        sa.Column("relative_momentum_zscore", sa.Numeric(12, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_sector_relative_prediction_evaluated_at"),
    )
    op.create_index("ix_sector_relative_assessments_prediction_id", "sector_relative_assessments", ["prediction_id"])
    op.create_table(
        "sector_performance_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("sector", sa.String(length=128), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("sector_sample_count", sa.Integer(), nullable=False),
        sa.Column("sector_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("baseline_sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sector_performance_reports_sector", "sector_performance_reports", ["sector"])


def downgrade() -> None:
    op.drop_index("ix_sector_performance_reports_sector", table_name="sector_performance_reports")
    op.drop_table("sector_performance_reports")
    op.drop_index("ix_sector_relative_assessments_prediction_id", table_name="sector_relative_assessments")
    op.drop_table("sector_relative_assessments")

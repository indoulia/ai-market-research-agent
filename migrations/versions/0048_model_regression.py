"""add model_regression_checks table

Revision ID: 0048_model_regression
Revises: 0047_decision_trace

EPIC-M1.67: detect when a production model's real-world performance has
materially degraded relative to its own immutable baseline window.
Append-only, immutable check log -- a detected regression can never be
silently mutated back to healthy; a later check on fresh data is always a
new, separate row.
"""
from alembic import op
import sqlalchemy as sa

revision = "0048_model_regression"
down_revision = "0047_decision_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_regression_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_window_label", sa.String(length=128), nullable=False),
        sa.Column("baseline_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("baseline_sample_count", sa.Integer(), nullable=False),
        sa.Column("monitoring_window_label", sa.String(length=128), nullable=False),
        sa.Column("monitoring_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("monitoring_sample_count", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("segment_regressions", sa.JSON(), nullable=False),
        sa.Column("rollback_triggered", sa.Boolean(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detection_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_model_regression_checks_model_version", "model_regression_checks", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_model_regression_checks_model_version", table_name="model_regression_checks")
    op.drop_table("model_regression_checks")

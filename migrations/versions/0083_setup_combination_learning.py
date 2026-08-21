"""add setup_combination_reports table

Revision ID: 0083_setup_combination
Revises: 0082_stock_behavior

EPIC-M1.108: discover which combinations of setup signals (technical
buckets, regime, horizon) consistently produce useful positive
outcomes, with multiplicity correction against the combinatorial
explosion of testing many combinations at once.
"""
from alembic import op
import sqlalchemy as sa

revision = "0083_setup_combination"
down_revision = "0082_stock_behavior"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "setup_combination_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("combination_count_considered", sa.Integer(), nullable=False),
        sa.Column("multiplicity_trial_count", sa.Integer(), nullable=False),
        sa.Column("adjusted_margin", sa.Numeric(10, 6), nullable=False),
        sa.Column("combinations", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_setup_combination_reports_model_version", "setup_combination_reports", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_setup_combination_reports_model_version", table_name="setup_combination_reports")
    op.drop_table("setup_combination_reports")

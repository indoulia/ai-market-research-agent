"""add cost_quality_tradeoff_reports table

Revision ID: 0093_cost_quality
Revises: 0092_reproducibility_audit

EPIC-M1.116: optimize provider/model usage so prediction quality
improves without unnecessary cost, while never letting cost
optimization silently drop below the minimum quality policy M1.64
already established.
"""
from alembic import op
import sqlalchemy as sa

revision = "0093_cost_quality"
down_revision = "0092_reproducibility_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_quality_tradeoff_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("provider_candidates", sa.JSON(), nullable=False),
        sa.Column("recommended_provider_id", sa.String(length=64), nullable=True),
        sa.Column("best_free_provider_id", sa.String(length=64), nullable=True),
        sa.Column("quality_floor", sa.Numeric(10, 6), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cost_quality_tradeoff_reports_data_type", "cost_quality_tradeoff_reports", ["data_type"])


def downgrade() -> None:
    op.drop_index("ix_cost_quality_tradeoff_reports_data_type", table_name="cost_quality_tradeoff_reports")
    op.drop_table("cost_quality_tradeoff_reports")

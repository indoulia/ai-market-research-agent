"""add segment_abstention_quality_reports table

Revision ID: 0095_abstention_quality
Revises: 0094_merge_0093_heads

EPIC-M1.130: segment M1.111's published-vs-suppressed counterfactual
comparison by sector, market-cap, horizon and regime, so abstention
quality can be measured per segment instead of only as a platform-wide
average.
"""
from alembic import op
import sqlalchemy as sa

revision = "0095_abstention_quality"
down_revision = "0094_merge_0093_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "segment_abstention_quality_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("segment_breakdown", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("segment_abstention_quality_reports")

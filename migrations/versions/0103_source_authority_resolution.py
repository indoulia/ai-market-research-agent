"""add resolved_facts table

Revision ID: 0103_source_authority
Revises: 0102_market_calendar

EPIC-M1.127: resolve conflicting external facts using explicit source
authority, freshness, provenance and fact-type policies rather than
simple provider majority voting.
"""
from alembic import op
import sqlalchemy as sa

revision = "0103_source_authority"
down_revision = "0102_market_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resolved_facts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("fact_type", sa.String(length=32), nullable=False),
        sa.Column("stock_id", sa.BigInteger(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column("resolved_value_numeric", sa.Numeric(18, 6), nullable=True),
        sa.Column("resolved_value_text", sa.String(length=512), nullable=True),
        sa.Column("winning_source", sa.String(length=64), nullable=True),
        sa.Column("winning_source_authority_tier", sa.Numeric(6, 2), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("sources_considered", sa.JSON(), nullable=False),
        sa.Column("conflicting", sa.Boolean(), nullable=False),
        sa.Column("resolution_reason", sa.String(length=48), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "fact_type", "stock_id", "fact_key", "resolved_at", name="uq_resolved_fact_type_stock_key_resolved_at",
        ),
    )
    op.create_index("ix_resolved_facts_fact_type", "resolved_facts", ["fact_type"])
    op.create_index("ix_resolved_facts_stock_id", "resolved_facts", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_resolved_facts_stock_id", table_name="resolved_facts")
    op.drop_index("ix_resolved_facts_fact_type", table_name="resolved_facts")
    op.drop_table("resolved_facts")

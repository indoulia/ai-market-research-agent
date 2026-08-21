"""add fundamental and news provider consensus assessment tables

Revision ID: 0078_provider_consensus
Revises: 0077_regime_transition

EPIC-M1.103: use independent provider/evidence agreement or
disagreement as an explicit signal of prediction reliability and data
quality, now that M1.91 gives this platform genuinely independent
second providers for fundamental and news/event data.
"""
from alembic import op
import sqlalchemy as sa

revision = "0078_provider_consensus"
down_revision = "0077_regime_transition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fundamental_consensus_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.String(length=32), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("sources_considered", sa.JSON(), nullable=False),
        sa.Column("weighted_mean", sa.Numeric(18, 6), nullable=True),
        sa.Column("max_relative_deviation", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("trust_reduction_recommended", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consensus_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("stock_id", "period_end_date", "evaluated_at", name="uq_fundamental_consensus_stock_period_evaluated_at"),
    )
    op.create_index("ix_fundamental_consensus_assessments_stock_id", "fundamental_consensus_assessments", ["stock_id"])
    op.create_table(
        "news_consensus_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("anchor_published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distinct_source_count", sa.Integer(), nullable=False),
        sa.Column("distinct_headline_count", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consensus_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_news_consensus_assessments_stock_id", "news_consensus_assessments", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_news_consensus_assessments_stock_id", table_name="news_consensus_assessments")
    op.drop_table("news_consensus_assessments")
    op.drop_index("ix_fundamental_consensus_assessments_stock_id", table_name="fundamental_consensus_assessments")
    op.drop_table("fundamental_consensus_assessments")

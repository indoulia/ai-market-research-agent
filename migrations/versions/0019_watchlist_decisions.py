"""add watchlist_decisions table

Revision ID: 0019_watchlist_decisions
Revises: 0018_watchlist_entries

EPIC-M1.20: persists one immutable, purpose-built history record per M1.19
watchlist analysis -- flattening the M1.17 DiscoveryRecord / M1.13
RecommendationGeneration / Prediction rows that analysis already produced into
a single row so history can be queried deterministically by symbol and time
range without a fan-out join, and so the decision itself can never be rewritten.
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_watchlist_decisions"
down_revision = "0018_watchlist_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column(
            "recommendation_generation_id",
            sa.BigInteger(),
            sa.ForeignKey("recommendation_generations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("failed_criteria", sa.JSON(), nullable=True),
        sa.Column("consensus_contract_version", sa.String(length=32), nullable=False),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("feature_version", sa.String(length=64), nullable=True),
        sa.Column("scoring_contract_version", sa.String(length=32), nullable=True),
        sa.Column("horizon_selection_version", sa.String(length=32), nullable=True),
        sa.Column("opportunity_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("decision_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_watchlist_decisions_stock_id", "watchlist_decisions", ["stock_id"])
    op.create_index("ix_watchlist_decisions_decided_at", "watchlist_decisions", ["decided_at"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_decisions_decided_at", table_name="watchlist_decisions")
    op.drop_index("ix_watchlist_decisions_stock_id", table_name="watchlist_decisions")
    op.drop_table("watchlist_decisions")

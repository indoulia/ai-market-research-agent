"""add watchlist_evaluations table

Revision ID: 0009_watchlist_evaluations
Revises: 0008_consensus_contract_version

EPIC-M1.7: persists every watchlist evaluation as its own append-only row (never
updated), recording the M1.8 consensus contract version used, whether the candidate
qualified, which criteria failed if not, and the resulting recommendation if promoted.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_watchlist_evaluations"
down_revision = "0008_consensus_contract_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_evaluations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consensus_contract_version", sa.String(32), nullable=False),
        sa.Column("qualifies", sa.Boolean(), nullable=False),
        sa.Column("failed_criteria", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("backlog_reason", sa.String(64), nullable=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("watchlist_evaluations")

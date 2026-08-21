"""add user_holdings table

Revision ID: 0041_user_holdings
Revises: 0040_position_risk_assessment

EPIC-M1.59: an append-only log of user-declared portfolio holdings
(HELD/SOLD events) -- there is no brokerage integration in this repo, so a
holding is only ever what the user explicitly declares, never inferred or
fabricated. "Current holdings" is derived by reading the latest event per
(user_id, stock_id), never by mutating a prior row.
"""
from alembic import op
import sqlalchemy as sa

revision = "0041_user_holdings"
down_revision = "0040_position_risk_assessment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_holdings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_holdings_user_id", "user_holdings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_holdings_user_id", table_name="user_holdings")
    op.drop_table("user_holdings")

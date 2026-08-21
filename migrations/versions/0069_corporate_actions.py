"""add corporate_actions table

Revision ID: 0069_corporate_actions
Revises: 0068_label_version

EPIC-M1.96: record splits, bonuses, rights, dividends, symbol changes,
mergers, demergers and delistings as immutable, versioned historical
fact, so historical prices/returns/identities remain economically
correct and traceable across corporate actions.
"""
from alembic import op
import sqlalchemy as sa

revision = "0069_corporate_actions"
down_revision = "0068_label_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("ratio", sa.Numeric(12, 6), nullable=True),
        sa.Column("cash_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("old_symbol", sa.String(length=32), nullable=True),
        sa.Column("new_symbol", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("action_version", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_corporate_actions_stock_id", "corporate_actions", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_corporate_actions_stock_id", table_name="corporate_actions")
    op.drop_table("corporate_actions")

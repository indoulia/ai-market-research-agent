"""add Upstox instrument key to stocks

Revision ID: 0002_upstox_instrument_key
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_upstox_instrument_key"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stocks", sa.Column("instrument_key", sa.String(length=128), nullable=True))
    op.create_index("ix_stocks_instrument_key", "stocks", ["instrument_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_stocks_instrument_key", table_name="stocks")
    op.drop_column("stocks", "instrument_key")

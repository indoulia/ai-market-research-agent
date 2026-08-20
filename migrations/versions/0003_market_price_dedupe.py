"""enforce one daily candle per stock and timestamp

Revision ID: 0003_market_price_dedupe
Revises: 0002_upstox_instrument_key
"""
from alembic import op

revision = "0003_market_price_dedupe"
down_revision = "0002_upstox_instrument_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_market_prices_stock_timestamp",
        "market_prices",
        ["stock_id", "timestamp"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_market_prices_stock_timestamp", table_name="market_prices")

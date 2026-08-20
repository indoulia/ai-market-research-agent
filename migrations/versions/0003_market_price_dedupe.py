"""enforce one daily candle per stock and timestamp

Revision ID: 0003_market_price_dedupe
Revises: 0002_upstox_instrument_key

EPIC-M1.4-SUB-02: `0001_initial` already creates a table-level `UniqueConstraint`
named `uq_market_prices_stock_timestamp` on `(stock_id, timestamp)`, which PostgreSQL
backs with an identically-named unique index automatically. This migration's original
body called `op.create_index` under that same name, which always fails with
"relation already exists" on a genuinely fresh database -- no environment has ever
applied this migration's original body successfully; every prior validation worked
around the failure by `alembic stamp`-ing past this revision instead of running it.
The intended one-candle-per-stock-per-day uniqueness is already enforced by 0001's
constraint, so this revision is now a documented no-op, letting a fresh database reach
head via a real `alembic upgrade head` without stamping.
"""
from alembic import op

revision = "0003_market_price_dedupe"
down_revision = "0002_upstox_instrument_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

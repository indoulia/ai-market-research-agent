"""add nullable provider_id column to data_fetch_attempts

Revision ID: 0067_provider_id
Revises: 0066_usefulness_assessment

EPIC-M1.93: DataFetchAttempt (M1.35) recorded only data_type/scope_key,
with no way to tell which concrete provider (Yahoo, Stooq, Alpha Vantage,
Finnhub, ...) made a given attempt. This additive, nullable column lets
provider-level quality/reliability be measured without touching any
already-persisted row -- existing rows simply have provider_id = NULL,
honestly meaning "provider identity not recorded at the time".
"""
from alembic import op
import sqlalchemy as sa

revision = "0067_provider_id"
down_revision = "0066_usefulness_assessment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_fetch_attempts", sa.Column("provider_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("data_fetch_attempts", "provider_id")

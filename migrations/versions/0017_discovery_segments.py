"""add stock industry/market_cap columns and discovery_segments table

Revision ID: 0017_discovery_segments
Revises: 0016_discovery_records

EPIC-M1.34: adds the classification fields (`industry`, `market_cap`) needed
alongside the existing `sector` column to segment discovery by market-cap,
sector, industry, and liquidity, plus a `discovery_segments` table persisting
an immutable snapshot of a candidate's segment membership at discovery time.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_discovery_segments"
down_revision = "0016_discovery_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stocks", sa.Column("industry", sa.String(length=128), nullable=True))
    op.add_column("stocks", sa.Column("market_cap", sa.Numeric(20, 2), nullable=True))

    op.create_table(
        "discovery_segments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "discovery_record_id",
            sa.BigInteger(),
            sa.ForeignKey("discovery_records.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("market_cap_bucket", sa.String(length=32), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=False),
        sa.Column("industry", sa.String(length=128), nullable=False),
        sa.Column("liquidity_bucket", sa.String(length=32), nullable=False),
        sa.Column("segmentation_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("discovery_segments")
    op.drop_column("stocks", "market_cap")
    op.drop_column("stocks", "industry")

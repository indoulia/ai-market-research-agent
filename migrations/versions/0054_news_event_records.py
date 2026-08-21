"""add news_event_records table

Revision ID: 0054_news_event_records
Revises: 0053_fundamental_data

EPIC-M1.73: real, point-in-time news/corporate-event ingestion. Unique
per (stock_id, external_id) so a repeat fetch of an already-seen article
for the same security is a no-op, not a duplicate row. Immutable once
created.
"""
from alembic import op
import sqlalchemy as sa

revision = "0054_news_event_records"
down_revision = "0053_fundamental_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_event_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("headline", sa.String(length=512), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("materiality", sa.String(length=16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("stock_id", "external_id", name="uq_news_event_stock_external_id"),
    )
    op.create_index("ix_news_event_records_stock_id", "news_event_records", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_news_event_records_stock_id", table_name="news_event_records")
    op.drop_table("news_event_records")

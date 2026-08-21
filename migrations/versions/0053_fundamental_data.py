"""add fundamental_data_records table

Revision ID: 0053_fundamental_data
Revises: 0052_user_decisions

EPIC-M1.72: real, point-in-time fundamental-data ingestion. Append-only --
a revised filing is a new row with a later published_at/fetched_at, never
an edit of a prior snapshot, so point-in-time reads (published_at <=
as_of_timestamp) stay safe regardless of later revisions.
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_fundamental_data"
down_revision = "0052_user_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fundamental_data_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=True),
        sa.Column("revenue", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_income", sa.Numeric(20, 2), nullable=True),
        sa.Column("eps", sa.Numeric(12, 4), nullable=True),
        sa.Column("gross_margin", sa.Numeric(10, 6), nullable=True),
        sa.Column("operating_margin", sa.Numeric(10, 6), nullable=True),
        sa.Column("net_margin", sa.Numeric(10, 6), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(10, 4), nullable=True),
        sa.Column("free_cash_flow", sa.Numeric(20, 2), nullable=True),
        sa.Column("pe_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("price_to_book", sa.Numeric(10, 4), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fundamental_data_records_stock_id", "fundamental_data_records", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_fundamental_data_records_stock_id", table_name="fundamental_data_records")
    op.drop_table("fundamental_data_records")

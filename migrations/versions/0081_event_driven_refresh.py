"""add event_trigger_records table

Revision ID: 0081_event_trigger
Revises: 0080_prediction_freshness

EPIC-M1.106: trigger timely re-analysis when material external events
occur -- earnings/major news, corporate actions, price/volume shocks,
and market-regime changes -- rather than waiting only for scheduled
polling.
"""
from alembic import op
import sqlalchemy as sa

revision = "0081_event_trigger"
down_revision = "0080_prediction_freshness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_trigger_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("materiality_note", sa.String(length=64), nullable=True),
        sa.Column("affected_prediction_count", sa.Integer(), nullable=False),
        sa.Column("triggered_decision_ids", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("event_type", "source_table", "source_id", name="uq_event_trigger_source"),
    )
    op.create_index("ix_event_trigger_records_stock_id", "event_trigger_records", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_event_trigger_records_stock_id", table_name="event_trigger_records")
    op.drop_table("event_trigger_records")

"""add market calendar tables

Revision ID: 0102_market_calendar
Revises: 0101_portfolio_correlation

EPIC-M1.121: authoritative, versioned market-session and calendar
awareness (trading days, holidays, special sessions, unexpected
closures) so every MRA operation runs in the correct trading context.

Renumbered twice before merging, no schema change either time: first to
0101 (chained onto 0100_merge_0091_0099_heads, PR #239's merge of the
concurrent EPIC-M1.119/M1.129 0099 collision plus the long-dangling
QA-audit 0091_missing_fk_indexes head), then to 0102 after EPIC-M1.124
independently claimed 0101 onto the same 0100 in the same window.
"""
from alembic import op
import sqlalchemy as sa

revision = "0102_market_calendar"
down_revision = "0101_portfolio_correlation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_calendar_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("timezone_name", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calendar_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("exchange", "version_label", name="uq_market_calendar_exchange_version_label"),
    )
    op.create_index("ix_market_calendar_versions_exchange", "market_calendar_versions", ["exchange"])

    op.create_table(
        "market_holidays",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("calendar_version_id", sa.BigInteger(), sa.ForeignKey("market_calendar_versions.id"), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("calendar_version_id", "holiday_date", name="uq_market_holiday_version_date"),
    )
    op.create_index("ix_market_holidays_calendar_version_id", "market_holidays", ["calendar_version_id"])

    op.create_table(
        "market_special_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("calendar_version_id", sa.BigInteger(), sa.ForeignKey("market_calendar_versions.id"), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("pre_market_start", sa.Time(), nullable=True),
        sa.Column("open_time", sa.Time(), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=False),
        sa.Column("post_market_end", sa.Time(), nullable=True),
        sa.Column("description", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("calendar_version_id", "session_date", name="uq_market_special_session_version_date"),
    )
    op.create_index("ix_market_special_sessions_calendar_version_id", "market_special_sessions", ["calendar_version_id"])

    op.create_table(
        "market_unexpected_closures",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("closure_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("exchange", "closure_date", name="uq_market_unexpected_closure_exchange_date"),
    )
    op.create_index("ix_market_unexpected_closures_exchange", "market_unexpected_closures", ["exchange"])


def downgrade() -> None:
    op.drop_index("ix_market_unexpected_closures_exchange", table_name="market_unexpected_closures")
    op.drop_table("market_unexpected_closures")
    op.drop_index("ix_market_special_sessions_calendar_version_id", table_name="market_special_sessions")
    op.drop_table("market_special_sessions")
    op.drop_index("ix_market_holidays_calendar_version_id", table_name="market_holidays")
    op.drop_table("market_holidays")
    op.drop_index("ix_market_calendar_versions_exchange", table_name="market_calendar_versions")
    op.drop_table("market_calendar_versions")

"""add prediction_outcome_events table

Revision ID: 0099_prediction_outcome_monitor
Revises: 0098_purged_embargo_validation

EPIC-M1.119: real-time prediction outcome monitor -- an append-only,
immutable event log of target-hit, stop-loss-hit, horizon-expiry,
invalidation and data-unresolved observations, detected independently of
end-of-day batch processing.

Numbered 0099 rather than the 0098 this branch originally picked: by the
time this merges, a concurrent EPIC-M1.125 session's migration had
independently claimed 0098 onto 0097. Renumbered here -- no schema change.
"""
from alembic import op
import sqlalchemy as sa

revision = "0099_prediction_outcome_monitor"
down_revision = "0098_purged_embargo_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_outcome_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("prediction_version", sa.String(length=64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("monitor_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_prediction_outcome_events_prediction_id",
        "prediction_outcome_events",
        ["prediction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_outcome_events_prediction_id", table_name="prediction_outcome_events")
    op.drop_table("prediction_outcome_events")

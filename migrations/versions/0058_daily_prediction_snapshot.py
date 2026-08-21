"""add daily_prediction_snapshots table

Revision ID: 0058_daily_prediction_snapshot
Revises: 0057_prediction_trust_score

EPIC-M1.78: a thin, immutable, append-only index linking a prediction to
its already-immutable M1.66 decision trace and M1.77 trust score as of a
given calendar day -- never duplicating either's fields.
"""
from alembic import op
import sqlalchemy as sa

revision = "0058_daily_prediction_snapshot"
down_revision = "0057_prediction_trust_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_prediction_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("recommendation_decision_trace_id", sa.BigInteger(), sa.ForeignKey("recommendation_decision_traces.id"), nullable=True),
        sa.Column("prediction_trust_score_id", sa.BigInteger(), sa.ForeignKey("prediction_trust_scores.id"), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False),
        sa.Column("snapshotted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_daily_prediction_snapshots_prediction_id", "daily_prediction_snapshots", ["prediction_id"])
    op.create_index(
        "ix_daily_prediction_snapshots_prediction_date", "daily_prediction_snapshots", ["prediction_id", "snapshot_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_daily_prediction_snapshots_prediction_date", table_name="daily_prediction_snapshots")
    op.drop_index("ix_daily_prediction_snapshots_prediction_id", table_name="daily_prediction_snapshots")
    op.drop_table("daily_prediction_snapshots")

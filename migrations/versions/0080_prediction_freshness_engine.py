"""add prediction_freshness_decisions table

Revision ID: 0080_prediction_freshness
Revises: 0079_segment_calibration

EPIC-M1.105: continuously determine whether an active prediction
remains valid, composing M1.62's own revalidation outcome with the
newer M1.101 (feature/coverage drift) and M1.103 (provider consensus
disagreement) signals it predates.
"""
from alembic import op
import sqlalchemy as sa

revision = "0080_prediction_freshness"
down_revision = "0079_segment_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_freshness_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("revalidation_outcome", sa.String(length=32), nullable=False),
        sa.Column("triggers", sa.JSON(), nullable=False),
        sa.Column("re_analysis_recommended", sa.Boolean(), nullable=False),
        sa.Column("revision_trigger_reason", sa.String(length=64), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_prediction_freshness_prediction_evaluated_at"),
    )
    op.create_index("ix_prediction_freshness_decisions_prediction_id", "prediction_freshness_decisions", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_prediction_freshness_decisions_prediction_id", table_name="prediction_freshness_decisions")
    op.drop_table("prediction_freshness_decisions")

"""add evidence_conflict_resolutions table

Revision ID: 0046_evidence_conflict
Revises: 0045_recommendation_alerts

EPIC-M1.65: resolve or explicitly surface conflicting evidence for one
recommendation -- RESOLVED/UNRESOLVED/INSUFFICIENT_EVIDENCE, with every
source considered preserved for audit. Idempotent per
(prediction_id, resolved_at); never mutates M1.48's evidence snapshot or
Prediction itself.
"""
from alembic import op
import sqlalchemy as sa

revision = "0046_evidence_conflict"
down_revision = "0045_recommendation_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_conflict_resolutions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("conflict_count", sa.Integer(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("evidence_categories_considered", sa.JSON(), nullable=False),
        sa.Column("confidence_adjustment_ceiling", sa.Numeric(10, 8), nullable=True),
        sa.Column("blocks_qualification", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "resolved_at", name="uq_conflict_resolution_prediction_resolved_at"),
    )
    op.create_index("ix_evidence_conflict_resolutions_prediction_id", "evidence_conflict_resolutions", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_conflict_resolutions_prediction_id", table_name="evidence_conflict_resolutions")
    op.drop_table("evidence_conflict_resolutions")

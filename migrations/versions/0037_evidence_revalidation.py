"""add evidence_revalidation_checks table

Revision ID: 0037_evidence_revalidation
Revises: 0036_recommendation_feedback

EPIC-M1.54: an append-only, immutable audit log of every horizon-aware
freshness recheck performed against a M1.48 evidence snapshot item -- never
mutates the original snapshot, matches M1.35's `DataFetchAttempt` precedent
of recording every check attempt, not only the ones that trigger a
revalidation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_evidence_revalidation"
down_revision = "0036_recommendation_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_revalidation_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("recommendation_evidence_item_id", sa.BigInteger(), sa.ForeignKey("recommendation_evidence_items.id"), nullable=False),
        sa.Column("evidence_category", sa.String(length=32), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("freshness_threshold_seconds", sa.Integer(), nullable=False),
        sa.Column("revalidation_required", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("original_value", sa.String(length=64), nullable=True),
        sa.Column("current_value", sa.String(length=64), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revalidation_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_revalidation_checks_prediction_id", "evidence_revalidation_checks", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_revalidation_checks_prediction_id", table_name="evidence_revalidation_checks")
    op.drop_table("evidence_revalidation_checks")

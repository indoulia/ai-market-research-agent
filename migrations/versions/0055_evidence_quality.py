"""add evidence_quality_decisions table

Revision ID: 0055_evidence_quality
Revises: 0054_news_event_records

EPIC-M1.74: a single, per-recommendation evidence-completeness and
point-in-time data-quality gate over M1.48's evidence snapshot. Immutable,
append-only per (prediction_id, evaluated_at).
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_evidence_quality"
down_revision = "0054_news_event_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_quality_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("available_category_count", sa.Integer(), nullable=False),
        sa.Column("stale_category_count", sa.Integer(), nullable=False),
        sa.Column("unavailable_category_count", sa.Integer(), nullable=False),
        sa.Column("categories_considered", sa.JSON(), nullable=False),
        sa.Column("leaked_categories", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("confidence_adjustment_ceiling", sa.Numeric(10, 8), nullable=True),
        sa.Column("blocks_publication", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gate_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_evidence_quality_prediction_evaluated_at"),
    )
    op.create_index("ix_evidence_quality_decisions_prediction_id", "evidence_quality_decisions", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_quality_decisions_prediction_id", table_name="evidence_quality_decisions")
    op.drop_table("evidence_quality_decisions")

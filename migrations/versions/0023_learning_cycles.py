"""add learning_cycles table

Revision ID: 0023_learning_cycles
Revises: 0022_model_promotions

EPIC-M1.32: an append-only audit log of every continuous-learning cycle
attempt -- whether it ran the full discovery/calibration/evaluation/
promotion pipeline or was skipped for insufficient new evidence -- so the
cycle is resumable (each row records the outcome-id watermark it advanced
to) and every promoted/rejected model remains traceable back to the cycle
that produced it.
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_learning_cycles"
down_revision = "0022_model_promotions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_cycles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_outcomes_count", sa.Integer(), nullable=False),
        sa.Column("watermark_outcome_id", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("skip_reason", sa.String(length=64), nullable=True),
        sa.Column("discovery_effectiveness_version", sa.String(length=32), nullable=True),
        sa.Column("calibration_candidate_version", sa.String(length=32), nullable=True),
        sa.Column("candidate_model_evaluation_version", sa.String(length=32), nullable=True),
        sa.Column("model_promotion_id", sa.BigInteger(), sa.ForeignKey("model_promotions.id"), nullable=True),
        sa.Column("cycle_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("learning_cycles")

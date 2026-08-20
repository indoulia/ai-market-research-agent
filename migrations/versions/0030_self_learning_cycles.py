"""add self_learning_cycles table

Revision ID: 0030_self_learning_cycles
Revises: 0029_model_promotion_decisions

EPIC-M1.45: connects discovery, outcomes, learning-dataset construction
(M1.39), candidate model comparison (M1.43), and the safe promotion gate
(M1.44) into one repeatable, resumable, watermark-gated cycle -- the same
watermark-on-`PredictionOutcome.id` trigger M1.32 established, generalized to
this newer chain of EPICs.
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_self_learning_cycles"
down_revision = "0029_model_promotion_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "self_learning_cycles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_outcomes_count", sa.Integer(), nullable=False),
        sa.Column("watermark_outcome_id", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("skip_reason", sa.String(length=64), nullable=True),
        sa.Column("dataset_version", sa.String(length=32), nullable=True),
        sa.Column("comparison_version", sa.String(length=32), nullable=True),
        sa.Column("model_promotion_decision_id", sa.BigInteger(), sa.ForeignKey("model_promotion_decisions.id"), nullable=True),
        sa.Column("discovery_triggered", sa.Boolean(), nullable=False),
        sa.Column("cycle_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("self_learning_cycles")

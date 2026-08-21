"""add assumption_decay_assessments table

Revision ID: 0088_assumption_decay
Revises: 0087_counterfactual

EPIC-M1.112: detect when the assumptions behind an active prediction
have materially decayed with the passage of time, using M1.35's own
freshness policy applied against M1.48's frozen evidence-capture
timestamps re-checked at a later point.
"""
from alembic import op
import sqlalchemy as sa

revision = "0088_assumption_decay"
down_revision = "0087_counterfactual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assumption_decay_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("tracked_categories", sa.JSON(), nullable=False),
        sa.Column("decayed_categories", sa.JSON(), nullable=False),
        sa.Column("decay_ratio", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("invalidation_recommended", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decay_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_assumption_decay_prediction_evaluated_at"),
    )
    op.create_index("ix_assumption_decay_assessments_prediction_id", "assumption_decay_assessments", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_assumption_decay_assessments_prediction_id", table_name="assumption_decay_assessments")
    op.drop_table("assumption_decay_assessments")

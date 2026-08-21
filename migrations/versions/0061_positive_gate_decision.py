"""add positive_recommendation_gate_decisions table

Revision ID: 0061_positive_gate_decision
Revises: 0060_calibration_drift

EPIC-M1.81: a post-qualification gate requiring every later-computed
trust/evidence signal (M1.74, M1.77, M1.79, M1.80) to independently
pass before a prediction is positive-gate-eligible -- never a single
metric overriding the others. Immutable, idempotent per
(prediction_id, evaluated_at).
"""
from alembic import op
import sqlalchemy as sa

revision = "0061_positive_gate_decision"
down_revision = "0060_calibration_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positive_recommendation_gate_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("evidence_quality_met", sa.Boolean(), nullable=False),
        sa.Column("trust_quality_met", sa.Boolean(), nullable=False),
        sa.Column("segment_trust_met", sa.Boolean(), nullable=False),
        sa.Column("calibration_drift_met", sa.Boolean(), nullable=False),
        sa.Column("suppression_reasons", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gate_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_positive_gate_prediction_evaluated_at"),
    )
    op.create_index("ix_positive_gate_decisions_prediction_id", "positive_recommendation_gate_decisions", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_positive_gate_decisions_prediction_id", table_name="positive_recommendation_gate_decisions")
    op.drop_table("positive_recommendation_gate_decisions")

"""add trust_control_decisions table

Revision ID: 0064_trust_control_decision
Revises: 0063_prediction_stability

EPIC-M1.84: consolidates M1.77 trust, M1.79 segment reliability, M1.80
drift, M1.82 benchmark performance, and M1.83 stability/agreement into
one per-prediction control decision. Immutable, idempotent per
(prediction_id, evaluated_at).
"""
from alembic import op
import sqlalchemy as sa

revision = "0064_trust_control_decision"
down_revision = "0063_prediction_stability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trust_control_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("overall_trust_quality", sa.String(length=32), nullable=False),
        sa.Column("eligibility_reduced", sa.Boolean(), nullable=False),
        sa.Column("segment_trust_ok", sa.Boolean(), nullable=False),
        sa.Column("calibration_drift_ok", sa.Boolean(), nullable=False),
        sa.Column("benchmark_performance_ok", sa.Boolean(), nullable=False),
        sa.Column("stability_ok", sa.Boolean(), nullable=False),
        sa.Column("causes", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("control_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_trust_control_prediction_evaluated_at"),
    )
    op.create_index("ix_trust_control_decisions_prediction_id", "trust_control_decisions", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_trust_control_decisions_prediction_id", table_name="trust_control_decisions")
    op.drop_table("trust_control_decisions")

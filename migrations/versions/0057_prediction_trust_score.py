"""add prediction_trust_scores table

Revision ID: 0057_prediction_trust_score
Revises: 0056_horizon_probability

EPIC-M1.77: a dedicated, evidence-backed trust score per prediction,
combining M1.50 calibration quality, model-version historical accuracy,
M1.67 recent performance/drift, M1.75 horizon reliability, M1.41 regime
reliability, and M1.74 evidence quality -- distinct from score and
confidence. Append-only, immutable per (prediction_id, computed_at).
"""
from alembic import op
import sqlalchemy as sa

revision = "0057_prediction_trust_score"
down_revision = "0056_horizon_probability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_trust_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("overall_trust_score", sa.Numeric(10, 8), nullable=True),
        sa.Column("trust_quality", sa.String(length=32), nullable=False),
        sa.Column("calibration_component", sa.Numeric(10, 8), nullable=True),
        sa.Column("historical_accuracy_component", sa.Numeric(10, 8), nullable=True),
        sa.Column("recent_performance_component", sa.Numeric(10, 8), nullable=True),
        sa.Column("horizon_reliability_component", sa.Numeric(10, 8), nullable=True),
        sa.Column("regime_reliability_component", sa.Numeric(10, 8), nullable=True),
        sa.Column("evidence_quality_component", sa.Numeric(10, 8), nullable=True),
        sa.Column("available_component_count", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trust_score_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "computed_at", name="uq_prediction_trust_score_prediction_computed_at"),
    )
    op.create_index("ix_prediction_trust_scores_prediction_id", "prediction_trust_scores", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_prediction_trust_scores_prediction_id", table_name="prediction_trust_scores")
    op.drop_table("prediction_trust_scores")

"""add prediction_stability_assessments table

Revision ID: 0063_prediction_stability
Revises: 0062_quality_benchmark

EPIC-M1.83: measures revision-chain stability (composing M1.55's own
VersionComparison deltas) and cross-model-version agreement for one
recommendation lineage. Immutable, idempotent per
(original_prediction_id, assessed_at).
"""
from alembic import op
import sqlalchemy as sa

revision = "0063_prediction_stability"
down_revision = "0062_quality_benchmark"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_stability_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("original_prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("revision_count", sa.Integer(), nullable=False),
        sa.Column("max_score_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("max_confidence_delta", sa.Numeric(10, 8), nullable=True),
        sa.Column("unexplained_revision_count", sa.Integer(), nullable=False),
        sa.Column("stability_verdict", sa.String(length=32), nullable=False),
        sa.Column("model_agreement_verdict", sa.String(length=32), nullable=False),
        sa.Column("model_agreement_score_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("stability_backed_by_outcomes", sa.Boolean(), nullable=False),
        sa.Column("trust_reduction_recommended", sa.Boolean(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("original_prediction_id", "assessed_at", name="uq_stability_prediction_assessed_at"),
    )
    op.create_index("ix_prediction_stability_assessments_original_prediction_id", "prediction_stability_assessments", ["original_prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_prediction_stability_assessments_original_prediction_id", table_name="prediction_stability_assessments")
    op.drop_table("prediction_stability_assessments")

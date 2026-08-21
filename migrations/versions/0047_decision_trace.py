"""add recommendation_decision_traces table

Revision ID: 0047_decision_trace
Revises: 0046_evidence_conflict

EPIC-M1.66: consolidate every material input, version, and reason behind
one recommendation decision (qualified or rejected) into a single,
immutable, self-contained row -- so it can be reconstructed later without
needing to join across M1.4/M1.8/M1.13/M1.47/M1.48 or rely on their version
constants still existing in code. One row per recommendation_generation_id,
built once, never mutated.
"""
from alembic import op
import sqlalchemy as sa

revision = "0047_decision_trace"
down_revision = "0046_evidence_conflict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_decision_traces",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("recommendation_generation_id", sa.BigInteger(), sa.ForeignKey("recommendation_generations.id"), nullable=False),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("as_of_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sma20_distance", sa.Numeric(12, 6), nullable=True),
        sa.Column("volume_ratio_20d", sa.Numeric(12, 6), nullable=True),
        sa.Column("atr_percent", sa.Numeric(12, 6), nullable=True),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("target_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("stop_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("predicted_probability", sa.Numeric(10, 8), nullable=True),
        sa.Column("confidence", sa.Numeric(10, 8), nullable=True),
        sa.Column("opportunity_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("feature_version", sa.String(length=64), nullable=True),
        sa.Column("consensus_contract_version", sa.String(length=32), nullable=True),
        sa.Column("horizon_selection_version", sa.String(length=32), nullable=True),
        sa.Column("scoring_contract_version", sa.String(length=32), nullable=True),
        sa.Column("target_stop_methodology_version", sa.String(length=32), nullable=True),
        sa.Column("target_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("stop_loss_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("qualification_outcome", sa.String(length=32), nullable=False),
        sa.Column("rejection_reasons", sa.JSON(), nullable=True),
        sa.Column("evidence_categories_snapshot", sa.JSON(), nullable=False),
        sa.Column("traced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_trace_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("recommendation_generation_id", name="uq_decision_trace_generation"),
    )
    op.create_index("ix_recommendation_decision_traces_prediction_id", "recommendation_decision_traces", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_decision_traces_prediction_id", table_name="recommendation_decision_traces")
    op.drop_table("recommendation_decision_traces")

"""add regime transition/uncertainty and transition performance tables

Revision ID: 0077_regime_transition
Revises: 0076_feature_drift

EPIC-M1.102: detect unstable market-regime transitions and separate
market uncertainty from data/model uncertainty so Trust Score and
positive-only gating can respond appropriately.
"""
from alembic import op
import sqlalchemy as sa

revision = "0077_regime_transition"
down_revision = "0076_feature_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regime_transition_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column("previous_scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=True),
        sa.Column("current_regime", sa.String(length=32), nullable=False),
        sa.Column("previous_regime", sa.String(length=32), nullable=True),
        sa.Column("transition_detected", sa.Boolean(), nullable=False),
        sa.Column("distance_to_boundary", sa.Numeric(10, 6), nullable=False),
        sa.Column("boundary_instability_verdict", sa.String(length=32), nullable=False),
        sa.Column("uncertainty_source", sa.String(length=32), nullable=False),
        sa.Column("trust_reduction_recommended", sa.Boolean(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scan_id", name="uq_regime_transition_scan"),
    )
    op.create_table(
        "prediction_regime_uncertainty_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("regime_transition_assessment_id", sa.BigInteger(), sa.ForeignKey("regime_transition_assessments.id"), nullable=False),
        sa.Column("snapshotted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", name="uq_regime_uncertainty_snapshot_prediction"),
    )
    op.create_table(
        "transition_period_performance_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("transition_sample_count", sa.Integer(), nullable=False),
        sa.Column("transition_success_count", sa.Integer(), nullable=False),
        sa.Column("transition_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("stable_sample_count", sa.Integer(), nullable=False),
        sa.Column("stable_success_count", sa.Integer(), nullable=False),
        sa.Column("stable_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("success_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("transition_period_performance_reports")
    op.drop_table("prediction_regime_uncertainty_snapshots")
    op.drop_table("regime_transition_assessments")

"""add feature reference/drift and coverage drift tables

Revision ID: 0076_feature_drift
Revises: 0075_experiment_integrity

EPIC-M1.101: detect changes in feature distributions and evidence
coverage that can make a previously reliable model less trustworthy
before outcome-based regression becomes visible.
"""
from alembic import op
import sqlalchemy as sa

revision = "0076_feature_drift"
down_revision = "0075_experiment_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_reference_distributions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_name", sa.String(length=64), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("mean", sa.Numeric(18, 8), nullable=False),
        sa.Column("stdev", sa.Numeric(18, 8), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("model_version", "feature_name", name="uq_feature_reference_model_feature"),
    )
    op.create_index("ix_feature_reference_distributions_model_version", "feature_reference_distributions", ["model_version"])
    op.create_table(
        "feature_drift_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_name", sa.String(length=64), nullable=False),
        sa.Column("monitoring_window_label", sa.String(length=128), nullable=False),
        sa.Column("monitoring_sample_count", sa.Integer(), nullable=False),
        sa.Column("monitoring_mean", sa.Numeric(18, 8), nullable=True),
        sa.Column("drift_magnitude", sa.Numeric(18, 8), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("trust_reduction_recommended", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drift_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("model_version", "feature_name", "evaluated_at", name="uq_feature_drift_model_feature_evaluated_at"),
    )
    op.create_index("ix_feature_drift_assessments_model_version", "feature_drift_assessments", ["model_version"])
    op.create_table(
        "coverage_drift_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("reference_window_label", sa.String(length=128), nullable=False),
        sa.Column("monitoring_window_label", sa.String(length=128), nullable=False),
        sa.Column("reference_sample_count", sa.Integer(), nullable=False),
        sa.Column("monitoring_sample_count", sa.Integer(), nullable=False),
        sa.Column("reference_coverage_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("monitoring_coverage_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("coverage_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("trust_reduction_recommended", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drift_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("model_version", "evaluated_at", name="uq_coverage_drift_model_evaluated_at"),
    )
    op.create_index("ix_coverage_drift_assessments_model_version", "coverage_drift_assessments", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_coverage_drift_assessments_model_version", table_name="coverage_drift_assessments")
    op.drop_table("coverage_drift_assessments")
    op.drop_index("ix_feature_drift_assessments_model_version", table_name="feature_drift_assessments")
    op.drop_table("feature_drift_assessments")
    op.drop_index("ix_feature_reference_distributions_model_version", table_name="feature_reference_distributions")
    op.drop_table("feature_reference_distributions")

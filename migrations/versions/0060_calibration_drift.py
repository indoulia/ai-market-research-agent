"""add prediction_calibration_drifts table

Revision ID: 0060_calibration_drift
Revises: 0059_horizon_regime_trust

EPIC-M1.80: detects prediction-distribution and calibration drift
between two disjoint evaluation windows for one model version, composing
(not duplicating) M1.67's own regression check for the horizon/regime
segmentation dimension. Append-only check log.
"""
from alembic import op
import sqlalchemy as sa

revision = "0060_calibration_drift"
down_revision = "0059_horizon_regime_trust"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_calibration_drifts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_window_label", sa.String(length=128), nullable=False),
        sa.Column("baseline_sample_count", sa.Integer(), nullable=False),
        sa.Column("monitoring_window_label", sa.String(length=128), nullable=False),
        sa.Column("monitoring_sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_mean_predicted_probability", sa.Numeric(10, 8), nullable=True),
        sa.Column("monitoring_mean_predicted_probability", sa.Numeric(10, 8), nullable=True),
        sa.Column("distribution_drift", sa.Numeric(10, 8), nullable=True),
        sa.Column("distribution_drift_detected", sa.Boolean(), nullable=False),
        sa.Column("baseline_calibration_error", sa.Numeric(10, 8), nullable=True),
        sa.Column("monitoring_calibration_error", sa.Numeric(10, 8), nullable=True),
        sa.Column("calibration_drift", sa.Numeric(10, 8), nullable=True),
        sa.Column("calibration_drift_detected", sa.Boolean(), nullable=False),
        sa.Column("model_regression_check_id", sa.BigInteger(), sa.ForeignKey("model_regression_checks.id"), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("trust_reduction_recommended", sa.Boolean(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drift_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prediction_calibration_drifts_model_version", "prediction_calibration_drifts", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_prediction_calibration_drifts_model_version", table_name="prediction_calibration_drifts")
    op.drop_table("prediction_calibration_drifts")

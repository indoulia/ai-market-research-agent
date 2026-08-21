"""add experiments, experiment_arms, experiment_results tables

Revision ID: 0049_experiments
Revises: 0048_model_regression

EPIC-M1.68: isolated, versioned framework for comparing recommendation
models/scoring rules/evidence strategies without touching production
Prediction/PredictionOutcome tables. Experiment and ExperimentArm are
immutable configuration once created; ExperimentResult is an append-only
log of computed metrics per run.
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_experiments"
down_revision = "0048_model_regression"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("hypothesis", sa.String(length=2048), nullable=False),
        sa.Column("experiment_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_experiment_name"),
    )

    op.create_table(
        "experiment_arms",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("experiment_id", sa.BigInteger(), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("arm_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("horizon_days_filter", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("experiment_id", "arm_name", name="uq_experiment_arm_name"),
    )
    op.create_index("ix_experiment_arms_experiment_id", "experiment_arms", ["experiment_id"])

    op.create_table(
        "experiment_results",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("experiment_arm_id", sa.BigInteger(), sa.ForeignKey("experiment_arms.id"), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_drawdown", sa.Numeric(10, 6), nullable=True),
        sa.Column("calibration_error", sa.Numeric(10, 6), nullable=True),
        sa.Column("consistency_stdev", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("arm_config_snapshot", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("framework_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_experiment_results_experiment_arm_id", "experiment_results", ["experiment_arm_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_results_experiment_arm_id", table_name="experiment_results")
    op.drop_table("experiment_results")
    op.drop_index("ix_experiment_arms_experiment_id", table_name="experiment_arms")
    op.drop_table("experiment_arms")
    op.drop_table("experiments")

"""add feedback_driven_experiments table

Revision ID: 0050_feedback_experiments
Revises: 0049_experiments

EPIC-M1.69: links a recurring, statistically-meaningful user feedback
pattern to the M1.68 experiment it spawned, so every experiment created
this way identifies its feedback source. Immutable once created; one row
per (feedback_category, feedback_reason_code) pattern, ever.
"""
from alembic import op
import sqlalchemy as sa

revision = "0050_feedback_experiments"
down_revision = "0049_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_driven_experiments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("experiment_id", sa.BigInteger(), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("feedback_category", sa.String(length=64), nullable=False),
        sa.Column("feedback_reason_code", sa.String(length=64), nullable=False),
        sa.Column("evaluated_count_at_creation", sa.Integer(), nullable=False),
        sa.Column("distinct_user_count_at_creation", sa.Integer(), nullable=False),
        sa.Column("repeated_prediction_count_at_creation", sa.Integer(), nullable=False),
        sa.Column("success_rate_at_creation", sa.Numeric(10, 6), nullable=True),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("experiment_id", name="uq_feedback_driven_experiment_experiment"),
        sa.UniqueConstraint("feedback_category", "feedback_reason_code", name="uq_feedback_driven_experiment_pattern"),
    )


def downgrade() -> None:
    op.drop_table("feedback_driven_experiments")

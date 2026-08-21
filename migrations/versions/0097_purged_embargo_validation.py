"""add validation_folds and temporal_validation_policy_decisions tables

Revision ID: 0097_purged_embargo_validation
Revises: 0096_release_readiness

EPIC-M1.125: make time-overlapping financial labels and dependent
observations safe for model evaluation by enforcing purged and embargoed
validation policies, and make the resulting fold membership reconstructable
for every experiment.
"""
from alembic import op
import sqlalchemy as sa

revision = "0097_purged_embargo_validation"
down_revision = "0096_release_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_folds",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("fold_index", sa.Integer(), nullable=False),
        sa.Column("train_window_label", sa.String(length=128), nullable=False),
        sa.Column("train_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("train_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_window_label", sa.String(length=128), nullable=False),
        sa.Column("validation_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validation_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("embargo_days", sa.Integer(), nullable=False),
        sa.Column("eligible_training_prediction_ids", sa.JSON(), nullable=False),
        sa.Column("excluded_prediction_ids", sa.JSON(), nullable=False),
        sa.Column("exclusion_reason_counts", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("framework_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("model_version", "fold_index", "computed_at", name="uq_validation_fold_model_index_computed_at"),
    )
    op.create_index("ix_validation_folds_model_version", "validation_folds", ["model_version"])

    op.create_table(
        "temporal_validation_policy_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("fold_ids", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("fail_reasons", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("model_version", "evaluated_at", name="uq_temporal_validation_policy_model_evaluated_at"),
    )
    op.create_index(
        "ix_temporal_validation_policy_decisions_model_version",
        "temporal_validation_policy_decisions",
        ["model_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_temporal_validation_policy_decisions_model_version", table_name="temporal_validation_policy_decisions")
    op.drop_table("temporal_validation_policy_decisions")
    op.drop_index("ix_validation_folds_model_version", table_name="validation_folds")
    op.drop_table("validation_folds")

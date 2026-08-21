"""add holdout registry/usage and multiplicity/confirmation guard tables

Revision ID: 0075_experiment_integrity
Revises: 0074_ranking_effectiveness

EPIC-M1.100: prevent the self-learning loop from selecting an apparently
superior model merely because many experiments were tried, and prevent
the final holdout period from ever being reused for iterative tuning.
"""
from alembic import op
import sqlalchemy as sa

revision = "0075_experiment_integrity"
down_revision = "0074_ranking_effectiveness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holdout_window_registry",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registry_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("label", name="uq_holdout_window_label"),
    )
    op.create_table(
        "holdout_usage_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("holdout_label", sa.String(length=128), nullable=False),
        sa.Column("experiment_arm_id", sa.BigInteger(), sa.ForeignKey("experiment_arms.id"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("holdout_label", name="uq_holdout_usage_label"),
    )
    op.create_table(
        "multiplicity_guard_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("trial_count", sa.Integer(), nullable=False),
        sa.Column("observed_success_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("weakness_margin", sa.Numeric(10, 6), nullable=False),
        sa.Column("adjusted_margin", sa.Numeric(10, 6), nullable=False),
        sa.Column("significant", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("guard_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("model_version", "evaluated_at", name="uq_multiplicity_guard_model_evaluated_at"),
    )
    op.create_index("ix_multiplicity_guard_decisions_model_version", "multiplicity_guard_decisions", ["model_version"])
    op.create_table(
        "independent_confirmation_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_window_label", sa.String(length=128), nullable=False),
        sa.Column("first_window_label", sa.String(length=128), nullable=False),
        sa.Column("confirmation_window_label", sa.String(length=128), nullable=False),
        sa.Column("first_window_verdict", sa.String(length=32), nullable=False),
        sa.Column("confirmation_window_verdict", sa.String(length=32), nullable=False),
        sa.Column("both_validated", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmation_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("model_version", "confirmed_at", name="uq_independent_confirmation_model_confirmed_at"),
    )
    op.create_index("ix_independent_confirmation_decisions_model_version", "independent_confirmation_decisions", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_independent_confirmation_decisions_model_version", table_name="independent_confirmation_decisions")
    op.drop_table("independent_confirmation_decisions")
    op.drop_index("ix_multiplicity_guard_decisions_model_version", table_name="multiplicity_guard_decisions")
    op.drop_table("multiplicity_guard_decisions")
    op.drop_table("holdout_usage_records")
    op.drop_table("holdout_window_registry")

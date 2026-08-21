"""add bias_guard_checks and bias_guard_overrides tables

Revision ID: 0070_bias_guard
Revises: 0069_corporate_actions

EPIC-M1.97: make look-ahead, post-decision-revision and unverified-
universe-membership bias detectable and blocking for training, replay
and evaluation workflows, with an explicit, auditable override path that
never rewrites the original blocked verdict.
"""
from alembic import op
import sqlalchemy as sa

revision = "0070_bias_guard"
down_revision = "0069_corporate_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bias_guard_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("workflow_type", sa.String(length=32), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("guard_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "workflow_type", "checked_at", name="uq_bias_guard_prediction_workflow_checked_at"),
    )
    op.create_index("ix_bias_guard_checks_prediction_id", "bias_guard_checks", ["prediction_id"])

    op.create_table(
        "bias_guard_overrides",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("check_id", sa.BigInteger(), sa.ForeignKey("bias_guard_checks.id"), nullable=False, unique=True),
        sa.Column("justification", sa.String(length=1024), nullable=False),
        sa.Column("authorized_by", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("override_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bias_guard_overrides")
    op.drop_index("ix_bias_guard_checks_prediction_id", table_name="bias_guard_checks")
    op.drop_table("bias_guard_checks")

"""add orchestration_execution_locks and orchestration_executions tables

Revision ID: 0097_event_sched_orchestration
Revises: 0096_release_readiness

EPIC-M1.118: centralized MRA event & schedule orchestration -- one
authoritative record of which operation ran, why (trigger type/source),
whether it is currently in flight (lock), and its full attempt/retry
history (execution log).

Revision id shortened from the original "0097_event_schedule_
orchestration" (33 chars) to fit alembic_version.version_num's
VARCHAR(32) column -- see the repo's own fresh-database migration test.
"""
from alembic import op
import sqlalchemy as sa

revision = "0097_event_sched_orchestration"
down_revision = "0096_release_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_execution_locks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("operation_name", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("orchestration_rule_version", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("operation_name", "scope_key", name="uq_orchestration_lock_operation_scope"),
    )

    op.create_table(
        "orchestration_executions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("operation_name", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_source", sa.String(length=128), nullable=True),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("dedup_key", sa.String(length=256), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_reason", sa.String(length=256), nullable=True),
        sa.Column("orchestration_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_orchestration_executions_dedup_key", "orchestration_executions", ["dedup_key"]
    )
    op.create_index(
        "ix_orchestration_executions_operation_name", "orchestration_executions", ["operation_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_orchestration_executions_operation_name", table_name="orchestration_executions")
    op.drop_index("ix_orchestration_executions_dedup_key", table_name="orchestration_executions")
    op.drop_table("orchestration_executions")
    op.drop_table("orchestration_execution_locks")

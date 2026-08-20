"""add data_fetch_attempts table

Revision ID: 0024_data_fetch_attempts
Revises: 0023_learning_cycles

EPIC-M1.35: an append-only, immutable audit log of every information-refresh
attempt (success or failure) per data type and scope, so fetch attempts and
failures are auditable and unnecessary duplicate fetches can be detected and
avoided.
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_data_fetch_attempts"
down_revision = "0023_learning_cycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_fetch_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=128), nullable=True),
        sa.Column("refresh_policy_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_data_fetch_attempts_type_scope", "data_fetch_attempts", ["data_type", "scope_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_data_fetch_attempts_type_scope", table_name="data_fetch_attempts")
    op.drop_table("data_fetch_attempts")

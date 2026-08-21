"""add auth_sessions table

Revision ID: 0089_auth_session
Revises: 0088_assumption_decay

EPIC-M1.145: a real, server-managed session lifecycle (issue/refresh/
revoke/expire) for the Flutter mobile and web clients. `previous_
session_id` links a refreshed session back to the one it rotated out,
so the full lineage of a login is reconstructable.

Renumbered twice due to concurrent-session collisions: 0087 (onto
0086_api_pref_profile, collided with M1.111's 0087_counterfactual_
analysis) -> 0088 (onto 0087_counterfactual, collided with an
0088_assumption_decay_tracker migration merged concurrently) -> this,
0089 (onto 0088_assumption_decay). No schema change each time.
"""
from alembic import op
import sqlalchemy as sa

revision = "0089_auth_session"
down_revision = "0088_assumption_decay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_session_id", sa.BigInteger(), sa.ForeignKey("auth_sessions.id"), nullable=True),
        sa.Column("session_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_token", name="uq_auth_session_token"),
    )
    op.create_index("ix_auth_sessions_session_token", "auth_sessions", ["session_token"])
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_session_token", table_name="auth_sessions")
    op.drop_table("auth_sessions")

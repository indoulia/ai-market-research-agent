"""add upstox_oauth_states and upstox_oauth_tokens tables

Revision ID: 0108_upstox_oauth
Revises: 0107_e2e_gate_v2

EPIC-MARKSY-0001: server-side storage for the Upstox OAuth
authorization-code flow -- short-lived CSRF `state` values and
append-only access-token records. No secret/token is ever exposed
through the API; this table is read only by app/upstox_oauth.py and
api/services/integrations_upstox.py's status projection.
"""
from alembic import op
import sqlalchemy as sa

revision = "0108_upstox_oauth"
down_revision = "0107_e2e_gate_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upstox_oauth_states",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_upstox_oauth_states_state", "upstox_oauth_states", ["state"], unique=True)

    op.create_table(
        "upstox_oauth_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("access_token", sa.String(length=2048), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False, server_default="Bearer"),
        sa.Column("upstox_user_id", sa.String(length=128), nullable=True),
        sa.Column("obtained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("upstox_oauth_tokens")
    op.drop_index("ix_upstox_oauth_states_state", table_name="upstox_oauth_states")
    op.drop_table("upstox_oauth_states")

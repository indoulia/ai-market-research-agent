"""add user_decisions table

Revision ID: 0052_user_decisions
Revises: 0051_preference_suggestions

EPIC-M1.71: records a user's own decision (acted on / dismissed /
deferred) against a specific recommendation generation. Append-only --
a changed mind is a new row, never an edit of a prior one -- so the full
decision lifecycle is preserved immutably.
"""
from alembic import op
import sqlalchemy as sa

revision = "0052_user_decisions"
down_revision = "0051_preference_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("recommendation_generation_id", sa.BigInteger(), sa.ForeignKey("recommendation_generations.id"), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.String(length=2000), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("journal_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_decisions_user_id", "user_decisions", ["user_id"])
    op.create_index("ix_user_decisions_generation_id", "user_decisions", ["recommendation_generation_id"])


def downgrade() -> None:
    op.drop_index("ix_user_decisions_generation_id", table_name="user_decisions")
    op.drop_index("ix_user_decisions_user_id", table_name="user_decisions")
    op.drop_table("user_decisions")

"""add user_preference_suggestions table

Revision ID: 0051_preference_suggestions
Revises: 0050_feedback_experiments

EPIC-M1.70: learned, suggested user preference changes derived from the
user's own revealed feedback patterns. Purely advisory -- this table is
never read by app.user_preferences, so a suggestion can never take effect
without the user explicitly calling set_user_preference. Append-only.
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_preference_suggestions"
down_revision = "0050_feedback_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preference_suggestions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("current_horizon_band", sa.String(length=32), nullable=True),
        sa.Column("suggested_horizon_band", sa.String(length=32), nullable=False),
        sa.Column("evidence_sample_count", sa.Integer(), nullable=False),
        sa.Column("evidence_agree_rate", sa.Numeric(10, 6), nullable=False),
        sa.Column("current_band_agree_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("rationale", sa.String(length=1024), nullable=False),
        sa.Column("suggested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("learning_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_preference_suggestions_user_id", "user_preference_suggestions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_preference_suggestions_user_id", table_name="user_preference_suggestions")
    op.drop_table("user_preference_suggestions")

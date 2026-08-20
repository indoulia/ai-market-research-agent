"""add user_preferences and recommendation_preference_snapshots tables

Revision ID: 0031_user_preferences
Revises: 0030_self_learning_cycles

EPIC-M1.46: user investment preferences. `user_preferences` is append-only
and versioned per user -- the most recent row for a `user_id` is that user's
current effective preference (the same "log is the pointer" pattern M1.31/
M1.44 already established), so "a user can change preferences" never mutates
a prior version. `recommendation_preference_snapshots` records, immutably,
the exact preference version in effect when one recommendation was evaluated
for one user -- preference changes never retroactively alter a historical
snapshot.
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_user_preferences"
down_revision = "0030_self_learning_cycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("horizon_band", sa.String(length=16), nullable=False),
        sa.Column("custom_horizon_days", sa.Integer(), nullable=True),
        sa.Column("risk_preference", sa.String(length=16), nullable=False),
        sa.Column("min_confidence_threshold", sa.Numeric(10, 8), nullable=False),
        sa.Column("preferred_sectors", sa.JSON(), nullable=True),
        sa.Column("preferred_market_cap_buckets", sa.JSON(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preference_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])

    op.create_table(
        "recommendation_preference_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("recommendation_generation_id", sa.BigInteger(), sa.ForeignKey("recommendation_generations.id"), nullable=False),
        sa.Column("user_preference_id", sa.BigInteger(), sa.ForeignKey("user_preferences.id"), nullable=False),
        sa.Column("horizon_band", sa.String(length=16), nullable=False),
        sa.Column("min_confidence_threshold", sa.Numeric(10, 8), nullable=False),
        sa.Column("matched_horizon", sa.Boolean(), nullable=False),
        sa.Column("met_min_confidence", sa.Boolean(), nullable=False),
        sa.Column("preference_match_boost", sa.Boolean(), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("snapshotted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preference_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "recommendation_generation_id", name="uq_pref_snapshot_user_generation"),
    )


def downgrade() -> None:
    op.drop_table("recommendation_preference_snapshots")
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_table("user_preferences")

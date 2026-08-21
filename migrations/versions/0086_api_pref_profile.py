"""add user_api_preference_profiles and feedback_idempotency_keys tables

Revision ID: 0086_api_pref_profile
Revises: 0085_lifecycle_capacity

EPIC-M1.141: persist the preference fields the API contract requires
(markets/industries/watchlist/notification/display preferences) that
have no existing domain home -- `app.user_preferences.UserPreference`
already owns horizon/risk/sector/market-cap-bucket preferences and is
reused unchanged for those. `feedback_idempotency_keys` maps a client-
supplied `Idempotency-Key` header to the feedback row it originally
created -- `app.recommendation_feedback.submit_feedback` is deliberately
non-idempotent (retains every feedback event), so this EPIC's own
"duplicate submissions are idempotent" AC is enforced at the API layer.

Renumbered twice due to concurrent-session migration-number collisions:
originally 0083 (onto 0082_stock_behavior, collided with EPIC-M1.109's
0083_setup_combination_learning) -> 0085 (onto 0084_sector_relative,
collided with EPIC-M1.110's 0085_prediction_lifecycle_capacity) -> this,
0086 (onto 0085_lifecycle_capacity). No schema change each time,
filename/revision-id/down_revision only.
"""
from alembic import op
import sqlalchemy as sa

revision = "0086_api_pref_profile"
down_revision = "0085_lifecycle_capacity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_api_preference_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("markets", sa.JSON(), nullable=False),
        sa.Column("industries", sa.JSON(), nullable=False),
        sa.Column("watchlist_symbols", sa.JSON(), nullable=False),
        sa.Column("notification_preferences", sa.JSON(), nullable=False),
        sa.Column("display_preferences", sa.JSON(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preference_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_api_preference_profiles_user_id", "user_api_preference_profiles", ["user_id"])

    op.create_table(
        "feedback_idempotency_keys",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("feedback_id", sa.BigInteger(), sa.ForeignKey("recommendation_feedback.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_feedback_idem_user_key"),
    )


def downgrade() -> None:
    op.drop_table("feedback_idempotency_keys")
    op.drop_index("ix_user_api_preference_profiles_user_id", table_name="user_api_preference_profiles")
    op.drop_table("user_api_preference_profiles")

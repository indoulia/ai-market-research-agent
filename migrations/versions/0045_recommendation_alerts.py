"""add user_alert_preferences and recommendation_alerts tables

Revision ID: 0045_recommendation_alerts
Revises: 0044_recommendation_reval

EPIC-M1.63: notify users only when a recommendation or market event
requires attention. `user_alert_preferences` is versioned and append-only,
mirroring M1.46/M1.60's own preference pattern. `recommendation_alerts` is
unique-constrained on (user_id, alert_type, source_table, source_id) so the
same underlying event can never generate a duplicate alert for the same
user.
"""
from alembic import op
import sqlalchemy as sa

revision = "0045_recommendation_alerts"
down_revision = "0044_recommendation_reval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_alert_preferences",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("muted_alert_types", sa.JSON(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_preference_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_alert_preferences_user_id", "user_alert_preferences", ["user_id"])

    op.create_table(
        "recommendation_alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=True),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "alert_type", "source_table", "source_id", name="uq_alert_user_type_source"),
    )
    op.create_index("ix_recommendation_alerts_user_id", "recommendation_alerts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_alerts_user_id", table_name="recommendation_alerts")
    op.drop_table("recommendation_alerts")
    op.drop_index("ix_user_alert_preferences_user_id", table_name="user_alert_preferences")
    op.drop_table("user_alert_preferences")

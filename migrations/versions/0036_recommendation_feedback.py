"""add recommendation_feedback table

Revision ID: 0036_recommendation_feedback
Revises: 0035_confidence_quality

EPIC-M1.52: structured, immutable user feedback on recommendation quality --
deliberately append-only with NO uniqueness constraint, since multiple
feedback events (even ones that look identical) must all be retained,
never deduplicated or collapsed. Never touches `PredictionOutcome`/
`OutcomeMeasurement` -- feedback is opinion, not objective outcome truth.
"""
from alembic import op
import sqlalchemy as sa

revision = "0036_recommendation_feedback"
down_revision = "0035_confidence_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.String(length=2000), nullable=True),
        sa.Column("feedback_stage", sa.String(length=16), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feedback_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recommendation_feedback_prediction_id", "recommendation_feedback", ["prediction_id"])
    op.create_index("ix_recommendation_feedback_user_id", "recommendation_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_feedback_user_id", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_prediction_id", table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")

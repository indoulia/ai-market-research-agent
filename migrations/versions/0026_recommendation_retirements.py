"""add recommendation_retirements table

Revision ID: 0026_recommendation_retirements
Revises: 0025_recommendation_observations

EPIC-M1.37: an immutable, one-row-per-prediction retirement event. "Archived"
is a derived, query-time classification (a retired recommendation whose
retention window has elapsed) rather than a second persisted state, so
archiving never requires moving or deleting any evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_recommendation_retirements"
down_revision = "0025_recommendation_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_retirements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False, unique=True
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retirement_reason", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_state_at_retirement", sa.String(length=32), nullable=False),
        sa.Column("retirement_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recommendation_retirements")

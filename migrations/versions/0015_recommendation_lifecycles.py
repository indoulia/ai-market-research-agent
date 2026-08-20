"""add recommendation_lifecycles table

Revision ID: 0015_recommendation_lifecycles
Revises: 0014_recommendation_selections

EPIC-M1.15: tracks each M1.14-selected recommendation through its lifecycle
(ISSUED -> AWAITING_HORIZON -> EVALUATED/UNEVALUABLE) so outcome evaluation can be
scheduled, retried, and resumed after interruption without re-evaluating a
recommendation that already reached a terminal state.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_recommendation_lifecycles"
down_revision = "0014_recommendation_selections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_lifecycles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "recommendation_generation_id",
            sa.BigInteger(),
            sa.ForeignKey("recommendation_generations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_rule_version", sa.String(length=32), nullable=False),
        sa.Column("outcome_id", sa.BigInteger(), sa.ForeignKey("prediction_outcomes.id"), nullable=True),
        sa.Column("check_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recommendation_lifecycles")

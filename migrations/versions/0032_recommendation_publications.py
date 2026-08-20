"""add recommendation_publications table

Revision ID: 0032_recommendation_publications
Revises: 0031_user_preferences

EPIC-M1.47: freezes an explicit, internally consistent target price,
stop-loss price, upside/downside percentage, and reward/risk ratio for a
prediction under a specific, versioned methodology. One row per
(prediction_id, methodology_version) -- a future methodology change produces
a new row under a new version, never a mutation of a previously published
one ("later changes become a new recommendation version").
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_recommendation_publications"
down_revision = "0031_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_publications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("target_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("stop_loss_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("upside_percentage", sa.Numeric(10, 6), nullable=False),
        sa.Column("downside_percentage", sa.Numeric(10, 6), nullable=False),
        sa.Column("reward_risk_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "methodology_version", name="uq_publication_prediction_methodology"),
    )
    op.create_index("ix_recommendation_publications_prediction_id", "recommendation_publications", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_publications_prediction_id", table_name="recommendation_publications")
    op.drop_table("recommendation_publications")

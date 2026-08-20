"""add recommendation_generations table

Revision ID: 0013_recommendation_generations
Revises: 0012_opportunity_score

EPIC-M1.13: persists the outcome of attempting to generate a positive
recommendation from an M1.12 scan candidate -- QUALIFIED (linked to the resulting
Prediction) or NOT_QUALIFIED (with the failed consensus criteria recorded) -- so a
failed candidate is never silently dropped or converted into a negative
recommendation, and generation stays idempotent per scan candidate.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_recommendation_generations"
down_revision = "0012_opportunity_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_generations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "scan_candidate_id",
            sa.BigInteger(),
            sa.ForeignKey("scan_candidates.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("consensus_contract_version", sa.String(length=32), nullable=False),
        sa.Column("failed_criteria", sa.JSON(), nullable=True),
        sa.Column(
            "prediction_id",
            sa.BigInteger(),
            sa.ForeignKey("predictions.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recommendation_generations")

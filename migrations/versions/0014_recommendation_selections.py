"""add recommendation_selections table

Revision ID: 0014_recommendation_selections
Revises: 0013_recommendation_generations

EPIC-M1.14: persists, per scan, the selection decision (selected or not, and why)
for every M1.13-qualified recommendation -- one row per (scan, recommendation
generation), so unselected qualifying candidates stay auditable rather than
disappearing, and re-selecting the same scan is idempotent.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_recommendation_selections"
down_revision = "0013_recommendation_generations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_selections",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column(
            "recommendation_generation_id",
            sa.BigInteger(),
            sa.ForeignKey("recommendation_generations.id"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("selection_reason", sa.String(length=32), nullable=False),
        sa.Column("selection_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "scan_id", "recommendation_generation_id", name="uq_selection_scan_generation"
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendation_selections")

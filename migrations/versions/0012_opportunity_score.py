"""add scoring_contract_version and opportunity_score to predictions

Revision ID: 0012_opportunity_score
Revises: 0011_daily_candidate_scan

EPIC-M1.9: persists which versioned scoring contract (app/scoring.py
CONTRACT_VERSION) produced this recommendation's opportunity score, and the score
itself, so ranking decisions stay traceable even as the scoring contract evolves.

Renumbered to 0012 (M1.9's own migration was originally 0009_opportunity_score, but
that PR never merged into main -- see EPIC-M1.12's completion report for the
resulting broken-chain defect this renumbering avoids repeating).
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_opportunity_score"
down_revision = "0011_daily_candidate_scan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("scoring_contract_version", sa.String(32), nullable=False, server_default="UNVERSIONED"),
    )
    op.add_column(
        "predictions",
        sa.Column("opportunity_score", sa.Numeric(6, 2), nullable=False, server_default="0"),
    )
    op.alter_column("predictions", "scoring_contract_version", server_default=None)
    op.alter_column("predictions", "opportunity_score", server_default=None)


def downgrade() -> None:
    op.drop_column("predictions", "opportunity_score")
    op.drop_column("predictions", "scoring_contract_version")

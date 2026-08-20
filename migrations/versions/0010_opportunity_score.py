"""add scoring_contract_version and opportunity_score to predictions

Revision ID: 0010_opportunity_score
Revises: 0009_performance_report

EPIC-M1.9: persists which versioned scoring contract (app/scoring.py
CONTRACT_VERSION) produced this recommendation's opportunity score, and the score
itself, so ranking decisions stay traceable even as the scoring contract evolves.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_opportunity_score"
down_revision = "0009_performance_report"
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

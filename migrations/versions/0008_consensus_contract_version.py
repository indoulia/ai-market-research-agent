"""add consensus_contract_version to predictions

Revision ID: 0008_consensus_contract_version
Revises: 0007_outcome_actual_return

EPIC-M1.8: persists which versioned positive-consensus contract (app/consensus.py
CONTRACT_VERSION) qualified this recommendation, so every recommendation's
qualifying decision stays traceable even as the contract evolves.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_consensus_contract_version"
down_revision = "0007_outcome_actual_return"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("consensus_contract_version", sa.String(32), nullable=False, server_default="UNVERSIONED"),
    )
    op.alter_column("predictions", "consensus_contract_version", server_default=None)


def downgrade() -> None:
    op.drop_column("predictions", "consensus_contract_version")

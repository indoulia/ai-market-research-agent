"""add confidence to predictions for recommendation history

Revision ID: 0005_prediction_confidence
Revises: 0004_dataset_validation_runs
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_prediction_confidence"
down_revision = "0004_dataset_validation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("confidence", sa.Numeric(10, 8), nullable=False, server_default="0"),
    )
    op.alter_column("predictions", "confidence", server_default=None)


def downgrade() -> None:
    op.drop_column("predictions", "confidence")

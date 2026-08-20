"""add actual_return and prediction_error to prediction_outcomes

Revision ID: 0006_outcome_actual_return
Revises: 0005_prediction_confidence
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_outcome_actual_return"
down_revision = "0005_prediction_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prediction_outcomes",
        sa.Column("actual_return", sa.Numeric(10, 6), nullable=False, server_default="0"),
    )
    op.add_column(
        "prediction_outcomes",
        sa.Column("prediction_error", sa.Numeric(10, 6), nullable=False, server_default="0"),
    )
    op.alter_column("prediction_outcomes", "actual_return", server_default=None)
    op.alter_column("prediction_outcomes", "prediction_error", server_default=None)


def downgrade() -> None:
    op.drop_column("prediction_outcomes", "prediction_error")
    op.drop_column("prediction_outcomes", "actual_return")

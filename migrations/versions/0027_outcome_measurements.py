"""add outcome_measurements table

Revision ID: 0027_outcome_measurements
Revises: 0026_recommendation_retirements

EPIC-M1.38: a versioned, immutable classification layer over M1.5's
`PredictionOutcome`, adding an explicit `NEUTRAL` category (between
`SUCCESS`/`FAILURE`) and a traceable measurement rule version -- neither of
which the underlying M1.5 outcome record carries.
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_outcome_measurements"
down_revision = "0026_recommendation_retirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcome_measurements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "prediction_outcome_id",
            sa.BigInteger(),
            sa.ForeignKey("prediction_outcomes.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("outcome_classification", sa.String(length=32), nullable=False),
        sa.Column("realized_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measurement_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("outcome_measurements")

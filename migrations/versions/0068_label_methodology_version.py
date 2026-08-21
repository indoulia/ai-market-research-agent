"""add nullable label_methodology_version column to prediction_outcomes

Revision ID: 0068_label_version
Revises: 0067_provider_id

EPIC-M1.95: preserve the label-generation methodology's version identity
with every outcome (AC: "historical labels cannot change when
methodology versions change"). Additive and nullable -- existing rows
have label_methodology_version = NULL, honestly meaning "not recorded at
the time", never backfilled with a guess.
"""
from alembic import op
import sqlalchemy as sa

revision = "0068_label_version"
down_revision = "0067_provider_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prediction_outcomes", sa.Column("label_methodology_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("prediction_outcomes", "label_methodology_version")

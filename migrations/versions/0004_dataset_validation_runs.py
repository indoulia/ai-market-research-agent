"""persist auditable market dataset validation reports

Revision ID: 0004_dataset_validation_runs
Revises: 0003_market_price_dedupe
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_dataset_validation_runs"
down_revision = "0003_market_price_dedupe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_validation_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("from_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("issue_count", sa.BigInteger(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dataset_validation_runs")

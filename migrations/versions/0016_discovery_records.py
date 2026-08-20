"""add discovery_records table

Revision ID: 0016_discovery_records
Revises: 0015_recommendation_lifecycles

EPIC-M1.17: persists externally (e.g. ChatGPT-assisted) discovered candidate stock
provenance -- source, timestamp, free-text rationale -- separately from any
recommendation evidence, and links to the resulting M1.13 recommendation generation
once the candidate is routed through the same quantitative evaluation as internally
discovered candidates.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_discovery_records"
down_revision = "0015_recommendation_lifecycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.String(length=2000), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recommendation_generation_id",
            sa.BigInteger(),
            sa.ForeignKey("recommendation_generations.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scan_id", "stock_id", "source", name="uq_discovery_scan_stock_source"),
    )


def downgrade() -> None:
    op.drop_table("discovery_records")

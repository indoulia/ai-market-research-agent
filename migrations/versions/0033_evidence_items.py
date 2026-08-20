"""add recommendation_evidence_items table

Revision ID: 0033_evidence_items
Revises: 0032_recommendation_publications

EPIC-M1.48: an immutable, per-category evidence snapshot captured at
recommendation time -- one row per (prediction_id, evidence_category) across
fundamental, news, event, market/sector, and technical/volume evidence.
Categories with no real data pipeline in this repo (fundamental, event) are
recorded as an explicit UNAVAILABLE status rather than fabricated, matching
M1.35's own honest-partial-coverage stance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_evidence_items"
down_revision = "0032_recommendation_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_evidence_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("evidence_category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("reference", sa.String(length=2000), nullable=True),
        sa.Column("evidence_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False),
        sa.Column("snapshot_rule_version", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evidence_category", name="uq_evidence_prediction_category"),
    )
    op.create_index("ix_recommendation_evidence_items_prediction_id", "recommendation_evidence_items", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_evidence_items_prediction_id", table_name="recommendation_evidence_items")
    op.drop_table("recommendation_evidence_items")

"""add model_promotions table

Revision ID: 0022_model_promotions
Revises: 0021_market_regimes

EPIC-M1.31: an append-only, immutable promotion-decision log. This table
itself is the "current production model" pointer (the most recent PROMOTED
row) and the rollback mechanism (every prior PROMOTED row remains queryable
forever) -- no separate model-registry state to keep atomic/consistent.
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_model_promotions"
down_revision = "0021_market_regimes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_promotions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_model_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_model_version", sa.String(length=64), nullable=True),
        sa.Column("evidence_report_version", sa.String(length=32), nullable=False),
        sa.Column("success_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decision_reason", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approver", sa.String(length=128), nullable=False),
        sa.Column("promotion_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_model_promotions_candidate_model_version", "model_promotions", ["candidate_model_version"])


def downgrade() -> None:
    op.drop_index("ix_model_promotions_candidate_model_version", table_name="model_promotions")
    op.drop_table("model_promotions")

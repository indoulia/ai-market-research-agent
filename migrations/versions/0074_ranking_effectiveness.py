"""add ranking_effectiveness_reports table

Revision ID: 0074_ranking_effectiveness
Revises: 0073_learning_hypotheses

EPIC-M1.99: measure whether M1.87's composite opportunity ranking
actually outperforms the simpler, already-production M1.14
opportunity-score-only selection, on real, already-resolved outcomes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0074_ranking_effectiveness"
down_revision = "0073_learning_hypotheses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ranking_effectiveness_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("composite_sample_count", sa.Integer(), nullable=False),
        sa.Column("composite_success_count", sa.Integer(), nullable=False),
        sa.Column("composite_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("alternative_sample_count", sa.Integer(), nullable=False),
        sa.Column("alternative_success_count", sa.Integer(), nullable=False),
        sa.Column("alternative_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("success_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effectiveness_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ranking_effectiveness_reports")

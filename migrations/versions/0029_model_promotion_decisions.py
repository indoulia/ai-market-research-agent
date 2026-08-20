"""add model_promotion_decisions table

Revision ID: 0029_model_promotion_decisions
Revises: 0028_historical_learning_records

EPIC-M1.44: an append-only, immutable promotion-decision log gating whether a
candidate model (evaluated by M1.43's same-period comparison) may become the
active model for a given dataset version. Mirrors M1.31's design: this table
itself is the "active model" pointer (the most recent PROMOTED row for a
dataset version) and the rollback mechanism (every prior PROMOTED row remains
queryable forever) -- no separate model-registry state to keep consistent.
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_model_promotion_decisions"
down_revision = "0028_historical_learning_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_promotion_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("dataset_version", sa.String(length=32), nullable=False),
        sa.Column("candidate_model_name", sa.String(length=64), nullable=False),
        sa.Column("comparison_version", sa.String(length=32), nullable=False),
        sa.Column("calibration_error_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decision_reason", sa.String(length=64), nullable=False),
        sa.Column("regressed_segment_dimension", sa.String(length=32), nullable=True),
        sa.Column("regressed_segment_key", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approver", sa.String(length=128), nullable=False),
        sa.Column("promotion_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_model_promotion_decisions_dataset_version", "model_promotion_decisions", ["dataset_version"]
    )
    op.create_index(
        "ix_model_promotion_decisions_candidate_model_name", "model_promotion_decisions", ["candidate_model_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_model_promotion_decisions_candidate_model_name", table_name="model_promotion_decisions")
    op.drop_index("ix_model_promotion_decisions_dataset_version", table_name="model_promotion_decisions")
    op.drop_table("model_promotion_decisions")

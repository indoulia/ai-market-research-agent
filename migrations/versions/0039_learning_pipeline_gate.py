"""add learning_pipeline_promotion_decisions table

Revision ID: 0039_learning_pipeline_gate
Revises: 0038_recommendation_revisions

EPIC-M1.57: the final safety gate deciding whether an M1.56 evidence-backed
adaptive-adjustment candidate may enter production recommendation behavior.
Append-only, immutable, PASS/FAIL/INSUFFICIENT_EVIDENCE decision log --
mirrors M1.31/M1.44's "the log is the pointer" pattern for rollback: the
most recent PASS decision for a given (source_signal, affected_condition)
is the active promotion; every prior decision remains queryable forever.
"""
from alembic import op
import sqlalchemy as sa

revision = "0039_learning_pipeline_gate"
down_revision = "0038_recommendation_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_pipeline_promotion_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_signal", sa.String(length=32), nullable=False),
        sa.Column("affected_condition", sa.String(length=256), nullable=False),
        sa.Column("candidate_version", sa.String(length=32), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("expected_impact", sa.Numeric(12, 6), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approver", sa.String(length=128), nullable=False),
        sa.Column("gate_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_learning_pipeline_promotion_decisions_source_condition",
        "learning_pipeline_promotion_decisions",
        ["source_signal", "affected_condition"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_pipeline_promotion_decisions_source_condition", table_name="learning_pipeline_promotion_decisions")
    op.drop_table("learning_pipeline_promotion_decisions")

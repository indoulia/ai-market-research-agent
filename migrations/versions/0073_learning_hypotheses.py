"""add learning_hypotheses table

Revision ID: 0073_learning_hypotheses
Revises: 0072_opportunity_rank

EPIC-M1.88: combine attribution failure-pattern and usefulness evidence
into controlled learning hypotheses, validated against a disjoint
out-of-sample monitoring window before any eligibility effect is
recommended.
"""
from alembic import op
import sqlalchemy as sa

revision = "0073_learning_hypotheses"
down_revision = "0072_opportunity_rank"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_hypotheses",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("hypothesis_category", sa.String(length=32), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("factor_value", sa.String(length=64), nullable=False),
        sa.Column("baseline_window_label", sa.String(length=64), nullable=False),
        sa.Column("monitoring_window_label", sa.String(length=64), nullable=False),
        sa.Column("baseline_sample_count", sa.Integer(), nullable=False),
        sa.Column("monitoring_sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("monitoring_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("proposed_action", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("eligibility_effect", sa.String(length=32), nullable=False),
        sa.Column("evidence_reference", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hypothesis_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "model_version", "hypothesis_category", "dimension", "factor_value", "generated_at",
            name="uq_learning_hypothesis_segment_generated_at",
        ),
    )
    op.create_index("ix_learning_hypotheses_model_version", "learning_hypotheses", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_learning_hypotheses_model_version", table_name="learning_hypotheses")
    op.drop_table("learning_hypotheses")

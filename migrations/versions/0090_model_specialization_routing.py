"""add specialization_routing_decisions table

Revision ID: 0090_specialization_routing
Revises: 0089_merge_0088_heads

EPIC-M1.113: decide, per specialization dimension and segment, whether
a candidate model version demonstrably outperforms the global
production model on that segment, with multiplicity correction against
testing many segments at once and a global fallback when evidence is
sparse.
"""
from alembic import op
import sqlalchemy as sa

revision = "0090_specialization_routing"
down_revision = "0089_merge_0088_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "specialization_routing_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("segment_key", sa.String(length=64), nullable=False),
        sa.Column("specialized_model_version", sa.String(length=64), nullable=False),
        sa.Column("global_model_version", sa.String(length=64), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("adjusted_margin", sa.Numeric(10, 6), nullable=False),
        sa.Column("baseline_window_label", sa.String(length=128), nullable=False),
        sa.Column("confirmation_window_label", sa.String(length=128), nullable=False),
        sa.Column("baseline_verdict", sa.String(length=32), nullable=False),
        sa.Column("confirmation_verdict", sa.String(length=32), nullable=False),
        sa.Column("specialized_sample_count", sa.Integer(), nullable=False),
        sa.Column("global_sample_count", sa.Integer(), nullable=False),
        sa.Column("routing_verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("routing_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "dimension", "segment_key", "specialized_model_version", "global_model_version", "computed_at",
            name="uq_specialization_routing_segment_models_computed_at",
        ),
    )


def downgrade() -> None:
    op.drop_table("specialization_routing_decisions")

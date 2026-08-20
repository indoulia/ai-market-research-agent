"""add recommendation_revisions table

Revision ID: 0038_recommendation_revisions
Revises: 0037_evidence_revalidation

EPIC-M1.55: an immutable, append-only chain of recommendation versions.
`Prediction` rows are already immutable (M1.4); a "revision" here always
means a brand-new `Prediction` (built through the same M1.9/M1.10/M1.13
pipeline with fresh inputs) linked as the next version of an existing one --
never a mutation of any prior `Prediction`. The `previous_prediction_id`
uniqueness constraint keeps the version chain strictly linear: a prediction
can be superseded by at most one next version.
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_recommendation_revisions"
down_revision = "0037_evidence_revalidation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_revisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("original_prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("previous_prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("revised_prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("revision_reason", sa.String(length=32), nullable=False),
        sa.Column("triggering_evidence_revalidation_check_id", sa.BigInteger(), sa.ForeignKey("evidence_revalidation_checks.id"), nullable=True),
        sa.Column("revised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("previous_prediction_id", name="uq_revision_previous_prediction"),
    )
    op.create_index("ix_recommendation_revisions_original_prediction_id", "recommendation_revisions", ["original_prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_revisions_original_prediction_id", table_name="recommendation_revisions")
    op.drop_table("recommendation_revisions")

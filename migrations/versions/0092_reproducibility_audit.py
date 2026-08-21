"""add reproducibility_audit_decisions table

Revision ID: 0092_reproducibility_audit
Revises: 0091_provider_outage

EPIC-M1.115: detect when a historical prediction's own captured
versions or evidence-provider identities have since drifted from the
platform's current state, making a literal replay non-reproducible
without that being a real regression.
"""
from alembic import op
import sqlalchemy as sa

revision = "0092_reproducibility_audit"
down_revision = "0091_provider_outage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reproducibility_audit_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("version_drifted_fields", sa.JSON(), nullable=False),
        sa.Column("provider_drifted_categories", sa.JSON(), nullable=False),
        sa.Column("reproducible", sa.Boolean(), nullable=False),
        sa.Column("audited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "audited_at", name="uq_reproducibility_audit_prediction_audited_at"),
    )
    op.create_index("ix_reproducibility_audit_decisions_prediction_id", "reproducibility_audit_decisions", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_reproducibility_audit_decisions_prediction_id", table_name="reproducibility_audit_decisions")
    op.drop_table("reproducibility_audit_decisions")

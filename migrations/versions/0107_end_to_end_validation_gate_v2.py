"""add end_to_end_validation_gate_reports table

Revision ID: 0107_e2e_gate_v2
Revises: 0106_microstructure_liquidity

EPIC-M1.131: end-to-end prediction validation gate v2 -- the final,
signed evidence report superseding/extending M1.117's own release
readiness gate. Revision id kept <=32 chars (see PR #231/#233's
StringDataRightTruncation lesson).

Numbered 0107 rather than 0106: by the time this merges, EPIC-M1.128's
migration had independently claimed 0106 onto the same 0105 base.
Renumbered here -- no schema change.
"""
from alembic import op
import sqlalchemy as sa

revision = "0107_e2e_gate_v2"
down_revision = "0106_microstructure_liquidity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "end_to_end_validation_gate_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("check_results", sa.JSON(), nullable=False),
        sa.Column("blocking_issues", sa.JSON(), nullable=False),
        sa.Column("overall_verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gate_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_end_to_end_validation_gate_reports_model_version",
        "end_to_end_validation_gate_reports",
        ["model_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_end_to_end_validation_gate_reports_model_version", table_name="end_to_end_validation_gate_reports")
    op.drop_table("end_to_end_validation_gate_reports")

"""add provider_outage_snapshots table

Revision ID: 0091_provider_outage
Revises: 0090_specialization_routing

EPIC-M1.114: preserve, over time, whether a data type's registered
providers were experiencing no, partial, or total degradation --
continuity history M1.94's own selection logic deliberately never
persists (it recomputes fresh from M1.93 on every call, by design).
"""
from alembic import op
import sqlalchemy as sa

revision = "0091_provider_outage"
down_revision = "0090_specialization_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_outage_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("total_registered_providers", sa.Integer(), nullable=False),
        sa.Column("healthy_provider_count", sa.Integer(), nullable=False),
        sa.Column("degraded_provider_count", sa.Integer(), nullable=False),
        sa.Column("degraded_provider_ids", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("data_type", "evaluated_at", name="uq_provider_outage_data_type_evaluated_at"),
    )
    op.create_index("ix_provider_outage_snapshots_data_type", "provider_outage_snapshots", ["data_type"])


def downgrade() -> None:
    op.drop_index("ix_provider_outage_snapshots_data_type", table_name="provider_outage_snapshots")
    op.drop_table("provider_outage_snapshots")

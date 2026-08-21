"""add prediction_lifecycle_snapshots and capacity_control_decisions tables

Revision ID: 0085_lifecycle_capacity
Revises: 0084_sector_relative

EPIC-M1.110: classify each prediction through a complete, immutable
lifecycle derived from already-existing evidence, and limit the user
feed to a controlled, ranked, deduplicated set of the strongest
positive opportunities.
"""
from alembic import op
import sqlalchemy as sa

revision = "0085_lifecycle_capacity"
down_revision = "0084_sector_relative"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_lifecycle_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("previous_state", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.String(length=256), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifecycle_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_prediction_lifecycle_prediction_evaluated_at"),
    )
    op.create_index("ix_prediction_lifecycle_snapshots_prediction_id", "prediction_lifecycle_snapshots", ["prediction_id"])
    op.create_table(
        "capacity_control_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("scan_id", sa.BigInteger(), sa.ForeignKey("daily_candidate_scans.id"), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("capacity_limit", sa.Integer(), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", "evaluated_at", name="uq_capacity_control_prediction_evaluated_at"),
    )
    op.create_index("ix_capacity_control_decisions_prediction_id", "capacity_control_decisions", ["prediction_id"])


def downgrade() -> None:
    op.drop_index("ix_capacity_control_decisions_prediction_id", table_name="capacity_control_decisions")
    op.drop_table("capacity_control_decisions")
    op.drop_index("ix_prediction_lifecycle_snapshots_prediction_id", table_name="prediction_lifecycle_snapshots")
    op.drop_table("prediction_lifecycle_snapshots")

"""add prediction_attribution_snapshots and factor_association_reports tables

Revision ID: 0065_attribution_snapshot
Revises: 0064_trust_control_decision

EPIC-M1.85: point-in-time attribution snapshots per prediction
(bucketed input factors + evidence availability + outcome, reusing
M1.66's already-captured decision trace) and an aggregate,
never-causal, association report over them.
"""
from alembic import op
import sqlalchemy as sa

revision = "0065_attribution_snapshot"
down_revision = "0064_trust_control_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_attribution_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("sma20_distance_bucket", sa.String(length=16), nullable=True),
        sa.Column("volume_ratio_bucket", sa.String(length=16), nullable=True),
        sa.Column("evidence_categories_available", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("snapshotted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attribution_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prediction_id", name="uq_attribution_snapshot_prediction"),
    )

    op.create_table(
        "factor_association_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scope_label", sa.String(length=128), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("factor_associations", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("factor_association_reports")
    op.drop_table("prediction_attribution_snapshots")

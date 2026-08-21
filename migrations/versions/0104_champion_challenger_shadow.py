"""add shadow_challenger_assessments, shadow_challenger_comparison_reports and champion_rollbacks tables

Revision ID: 0104_champion_challenger_shadow
Revises: 0103_information_latency

EPIC-M1.123: champion/challenger shadow validation & rollback.

Numbered 0104 rather than 0103: by the time this merges, EPIC-M1.126's
migration had independently claimed 0103 onto the same 0102 base.
Renumbered here -- no schema change.
"""
from alembic import op
import sqlalchemy as sa

revision = "0104_champion_challenger_shadow"
down_revision = "0103_information_latency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shadow_challenger_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("champion_prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("champion_model_version", sa.String(length=64), nullable=False),
        sa.Column("challenger_model_version", sa.String(length=64), nullable=False),
        sa.Column("challenger_predicted_probability", sa.Numeric(10, 8), nullable=False),
        sa.Column("challenger_confidence", sa.Numeric(10, 8), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shadow_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("champion_prediction_id", "challenger_model_version", name="uq_shadow_prediction_challenger"),
    )

    op.create_table(
        "shadow_challenger_comparison_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("challenger_model_version", sa.String(length=64), nullable=False),
        sa.Column("champion_model_version", sa.String(length=64), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("champion_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("challenger_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("success_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("champion_calibration_error", sa.Numeric(10, 6), nullable=True),
        sa.Column("challenger_calibration_error", sa.Numeric(10, 6), nullable=True),
        sa.Column("by_horizon", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comparison_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "champion_rollbacks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("rolled_back_model_version", sa.String(length=64), nullable=False),
        sa.Column("restored_model_version", sa.String(length=64), nullable=False),
        sa.Column("triggering_model_regression_check_id", sa.BigInteger(), sa.ForeignKey("model_regression_checks.id"), nullable=True),
        sa.Column("resulting_model_promotion_id", sa.BigInteger(), sa.ForeignKey("model_promotions.id"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approver", sa.String(length=128), nullable=False),
        sa.Column("rollback_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("rolled_back_model_version", "restored_model_version", name="uq_rollback_from_to"),
    )


def downgrade() -> None:
    op.drop_table("champion_rollbacks")
    op.drop_table("shadow_challenger_comparison_reports")
    op.drop_table("shadow_challenger_assessments")

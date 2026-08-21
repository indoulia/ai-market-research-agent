"""add stock_behavior_assessments table

Revision ID: 0082_stock_behavior
Revises: 0081_event_trigger

EPIC-M1.107: learn prediction reliability at the individual security
level (by horizon and regime) with hierarchical fallback to global
evidence, without letting sparse stock history create false confidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0082_stock_behavior"
down_revision = "0081_event_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_behavior_assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("resolved_level", sa.String(length=32), nullable=False),
        sa.Column("resolved_sample_count", sa.Integer(), nullable=False),
        sa.Column("observed_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("fallback_chain", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("behavior_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "stock_id", "model_version", "horizon_days", "regime", "evaluated_at",
            name="uq_stock_behavior_stock_model_horizon_regime_evaluated_at",
        ),
    )
    op.create_index("ix_stock_behavior_assessments_stock_id", "stock_behavior_assessments", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_behavior_assessments_stock_id", table_name="stock_behavior_assessments")
    op.drop_table("stock_behavior_assessments")

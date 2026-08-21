"""add horizon_probability_profiles table

Revision ID: 0056_horizon_probability
Revises: 0055_evidence_quality

EPIC-M1.75: calibrated, horizon-specific outcome-probability profiles
per (model_version, horizon_days) cohort. Append-only check log, mirrors
0048_model_regression's own shape.
"""
from alembic import op
import sqlalchemy as sa

revision = "0056_horizon_probability"
down_revision = "0055_evidence_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_probability_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("positive_return_probability", sa.Numeric(10, 6), nullable=True),
        sa.Column("target_hit_probability", sa.Numeric(10, 6), nullable=True),
        sa.Column("stop_hit_probability", sa.Numeric(10, 6), nullable=True),
        sa.Column("expected_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("downside_p10_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_horizon_probability_profiles_model_version", "horizon_probability_profiles", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_horizon_probability_profiles_model_version", table_name="horizon_probability_profiles")
    op.drop_table("horizon_probability_profiles")

"""add published_vs_suppressed_reports table

Revision ID: 0087_counterfactual
Revises: 0086_api_pref_profile

EPIC-M1.111: measure what would have happened to qualified-but-not-
selected candidates, using the exact same outcome definition as
published recommendations, to distinguish true selection skill from
merely avoiding difficult cases.

Numbered 0087 (chained onto 0086_api_pref_profile) rather than the
0086 this branch originally picked: by the time this merged, the
concurrent EPIC-M1.141 session had already resolved the 0085 head
collision on its own side by renumbering itself to 0086 onto
0085_lifecycle_capacity, restoring a single linear head before this
migration landed. No schema change here either way.
"""
from alembic import op
import sqlalchemy as sa

revision = "0087_counterfactual"
down_revision = "0086_api_pref_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "published_vs_suppressed_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("published_sample_count", sa.Integer(), nullable=False),
        sa.Column("published_success_count", sa.Integer(), nullable=False),
        sa.Column("published_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("suppressed_sample_count", sa.Integer(), nullable=False),
        sa.Column("suppressed_success_count", sa.Integer(), nullable=False),
        sa.Column("suppressed_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("success_rate_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("opportunity_cost_total", sa.Numeric(14, 6), nullable=False),
        sa.Column("avoided_loss_total", sa.Numeric(14, 6), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("published_vs_suppressed_reports")

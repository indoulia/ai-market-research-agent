"""add probabilistic_score_reports and release_readiness_reports tables

Revision ID: 0096_release_readiness
Revises: 0095_abstention_quality

EPIC-M1.117: prove the complete MRA prediction loop is measurable,
calibrated, reproducible, continuously monitored and safe to improve,
by compiling already-computed evidence from M1.95-M1.116 into one
explicit release-readiness decision, plus the one genuinely new metric
this platform didn't have yet -- Brier and log probabilistic scores.

Numbered 0096 (chained onto 0095_abstention_quality) rather than the
0095 this branch originally picked: by the time this merged, a
concurrent EPIC-M1.130 session's migration had independently claimed
0095 onto 0094_merge_0093_heads. Rebased onto the post-merge
origin/main and renumbered here -- no schema change.
"""
from alembic import op
import sqlalchemy as sa

revision = "0096_release_readiness"
down_revision = "0095_abstention_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "probabilistic_score_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("window_label", sa.String(length=128), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("brier_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("log_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_probabilistic_score_reports_model_version", "probabilistic_score_reports", ["model_version"])
    op.create_table(
        "release_readiness_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("check_results", sa.JSON(), nullable=False),
        sa.Column("blocking_issues", sa.JSON(), nullable=False),
        sa.Column("overall_verdict", sa.String(length=32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_release_readiness_reports_model_version", "release_readiness_reports", ["model_version"])


def downgrade() -> None:
    op.drop_index("ix_release_readiness_reports_model_version", table_name="release_readiness_reports")
    op.drop_table("release_readiness_reports")
    op.drop_index("ix_probabilistic_score_reports_model_version", table_name="probabilistic_score_reports")
    op.drop_table("probabilistic_score_reports")

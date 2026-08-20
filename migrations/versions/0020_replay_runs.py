"""add replay_runs table

Revision ID: 0020_replay_runs
Revises: 0019_watchlist_decisions

EPIC-M1.24: persists each historical-replay attempt -- point-in-time-safe
recomputation of a recommendation's consensus/score/horizon decision using
only market data that existed as of the original scan date -- so replay
differences from the original persisted decision are auditable and
attributable to a specific software/model version, and so a run with
unavailable historical data records an explicit limitation rather than a
fabricated result.
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_replay_runs"
down_revision = "0019_watchlist_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replay_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "recommendation_generation_id",
            sa.BigInteger(),
            sa.ForeignKey("recommendation_generations.id"),
            nullable=False,
        ),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limitation", sa.String(length=64), nullable=True),
        sa.Column("replayed_qualifies", sa.Boolean(), nullable=True),
        sa.Column("replayed_failed_criteria", sa.JSON(), nullable=True),
        sa.Column("replayed_opportunity_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("replayed_horizon_days", sa.Integer(), nullable=True),
        sa.Column("replayed_predicted_probability", sa.Numeric(10, 8), nullable=True),
        sa.Column("replayed_model_version", sa.String(length=64), nullable=True),
        sa.Column("replayed_feature_version", sa.String(length=64), nullable=True),
        sa.Column("replayed_consensus_contract_version", sa.String(length=32), nullable=True),
        sa.Column("replayed_scoring_contract_version", sa.String(length=32), nullable=True),
        sa.Column("replayed_horizon_selection_version", sa.String(length=32), nullable=True),
        sa.Column("matches_original", sa.Boolean(), nullable=True),
        sa.Column("replay_rule_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_replay_runs_recommendation_generation_id", "replay_runs", ["recommendation_generation_id"])


def downgrade() -> None:
    op.drop_index("ix_replay_runs_recommendation_generation_id", table_name="replay_runs")
    op.drop_table("replay_runs")

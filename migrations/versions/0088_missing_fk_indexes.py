"""add indexes on FK columns left unindexed since their introducing migration

Revision ID: 0088_missing_fk_indexes
Revises: 0087_immutability_hardening

Found in the 2026-08-21 QA/integration audit: these foreign-key columns were never
given a supporting index and aren't otherwise covered by a unique constraint that
happens to lead with them, so any lookup/join filtering on them alone forces a full
table scan. Adding the index only; no other schema change.
"""
from alembic import op

revision = "0088_missing_fk_indexes"
down_revision = "0087_immutability_hardening"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_positive_opportunity_rankings_stock_id", "positive_opportunity_rankings", ["stock_id"]),
    ("ix_regime_transition_assessments_previous_scan_id", "regime_transition_assessments", ["previous_scan_id"]),
    (
        "ix_prediction_regime_uncertainty_snapshots_assessment_id",
        "prediction_regime_uncertainty_snapshots",
        ["regime_transition_assessment_id"],
    ),
    ("ix_capacity_control_decisions_scan_id", "capacity_control_decisions", ["scan_id"]),
    ("ix_feedback_idempotency_keys_feedback_id", "feedback_idempotency_keys", ["feedback_id"]),
)


def upgrade() -> None:
    for index_name, table_name, columns in _INDEXES:
        op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    for index_name, table_name, _columns in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table_name)

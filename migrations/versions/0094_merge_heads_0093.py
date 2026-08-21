"""merge concurrent 0093 heads (cost_quality, prediction_reliability)

Revision ID: 0094_merge_0093_heads
Revises: 0093_cost_quality, 0093_prediction_reliability

Both `0093_cost_quality` (EPIC-M1.116) and `0093_prediction_reliability`
(EPIC-M1.122) chained onto `0092_reproducibility_audit` and merged to
main as sibling heads within the same window. Pure Alembic merge
revision, no schema change.
"""
from __future__ import annotations

revision = "0094_merge_0093_heads"
down_revision = ("0093_cost_quality", "0093_prediction_reliability")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

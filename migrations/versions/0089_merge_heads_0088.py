"""merge concurrent 0088 heads (assumption_decay, auth_session)

Revision ID: 0089_merge_0088_heads
Revises: 0088_assumption_decay, 0088_auth_session

Both `0088_assumption_decay` (EPIC-M1.112) and `0088_auth_session`
(EPIC-M1.145) chained onto `0087_counterfactual` and merged to main as
sibling heads within the same short window -- a genuine multi-session
collision where each session's own pre-merge `alembic heads` check ran
against a locally-fetched-but-not-pulled `origin/main` (fetch updates
remote refs, not the working tree's migration files), so neither check
could see the other's already-merged migration. Pure Alembic merge
revision, no schema change.
"""
from __future__ import annotations

revision = "0089_merge_0088_heads"
down_revision = ("0088_assumption_decay", "0088_auth_session")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

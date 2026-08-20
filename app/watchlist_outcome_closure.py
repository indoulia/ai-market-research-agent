"""EPIC-M1.21: ensure every eligible recommendation issued via the watchlist
path (M1.18-M1.20) reaches an explicit terminal outcome, by reusing M1.15's
lifecycle/scheduler machinery wholesale rather than building a second
outcome-closure mechanism.

M1.15's `ensure_lifecycle_entries_for_scan` only creates `RecommendationLifecycle`
rows for M1.14 `RecommendationSelection` rows -- the daily-scan selection path.
A watchlist-qualified recommendation never goes through M1.14 selection at all,
so it would otherwise never get tracked to closure. This module is that same
"create an ISSUED lifecycle row" step for the watchlist path; `advance_lifecycle`
/ `process_due_lifecycles` (M1.15, untouched) are the actual closure mechanism
for both paths -- trading-day horizon logic, SUCCESS/FAILURE/UNEVALUABLE
distinction, immutability of the original `Prediction`, and idempotent/
recoverable scheduling are exactly M1.15's existing, already-tested behavior.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .lifecycle import LIFECYCLE_VERSION, STATE_ISSUED
from .models import RecommendationLifecycle, WatchlistDecision
from .recommendation_generator import OUTCOME_QUALIFIED


def ensure_lifecycle_entry_for_watchlist_decision(
    session: Session, decision: WatchlistDecision
) -> RecommendationLifecycle | None:
    """Create an `ISSUED` lifecycle row for a qualifying watchlist decision's
    recommendation, so M1.15's `process_due_lifecycles` picks it up for closure
    exactly like an M1.14-selected recommendation. Returns `None` for a
    rejected decision (`outcome != QUALIFIED`) -- nothing was issued, so there
    is nothing to track to closure (scope item 1: only *eligible issued*
    recommendations are identified for closure). Idempotent by
    `recommendation_generation_id` uniqueness, the same guarantee M1.15's own
    `ensure_lifecycle_entries_for_scan` relies on -- including when a
    recommendation happens to already have a lifecycle row created via the
    M1.14 path for the same underlying `RecommendationGeneration`."""
    if decision.outcome != OUTCOME_QUALIFIED:
        return None

    existing = session.scalar(
        select(RecommendationLifecycle).where(
            RecommendationLifecycle.recommendation_generation_id == decision.recommendation_generation_id
        )
    )
    if existing is not None:
        return existing

    lifecycle = RecommendationLifecycle(
        recommendation_generation_id=decision.recommendation_generation_id,
        state=STATE_ISSUED,
        lifecycle_rule_version=LIFECYCLE_VERSION,
    )
    session.add(lifecycle)
    session.commit()
    session.refresh(lifecycle)
    return lifecycle


def ensure_lifecycle_entries_for_watchlist_decisions(
    session: Session, decisions: Iterable[WatchlistDecision]
) -> tuple[RecommendationLifecycle, ...]:
    created = [ensure_lifecycle_entry_for_watchlist_decision(session, decision) for decision in decisions]
    return tuple(lifecycle for lifecycle in created if lifecycle is not None)

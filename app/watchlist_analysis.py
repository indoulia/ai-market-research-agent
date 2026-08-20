"""EPIC-M1.19: evaluate active watchlist (M1.18) stocks through exactly the same
positive-consensus (M1.8), scoring (M1.9), and horizon (M1.10) pipeline as
internally scanned or externally discovered candidates -- via the identical
M1.17 `record_discovery` + `route_discovery_through_pipeline` entry points -- so
watchlist membership alone can never create a recommendation. This module adds
no new persisted state: it reuses `DiscoveryRecord` (tagged `SOURCE_WATCHLIST`)
and `RecommendationGeneration` wholesale, the same way M1.33's continuous-scan
orchestration does, and its only genuinely new behavior is gating on M1.18's
watchlist membership before routing.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from .discovery import SOURCE_WATCHLIST, record_discovery, route_discovery_through_pipeline
from .models import RecommendationGeneration
from .watchlist_intake import is_active


class StockNotOnWatchlistError(RuntimeError):
    """Raised when the requested stock is not currently active on the
    watchlist (M1.18) -- watchlist analysis only ever evaluates stocks a user
    or other source has actually asked to be watched, never an arbitrary one."""


def analyze_watchlist_stock(
    session: Session,
    *,
    scan_id: int,
    stock_id: int,
    as_of_timestamp: datetime,
    entry_price: Decimal,
    target_return: Decimal,
    stop_return: Decimal,
) -> RecommendationGeneration:
    """Evaluate one currently-active watchlist stock for scan `scan_id` through
    the real M1.13 generator, identically to M1.17's discovery routing.
    Idempotent for the same `(scan_id, stock_id)` (scope item 7): re-analysis
    returns the original result rather than re-evaluating or duplicating it.
    Raises `StockNotOnWatchlistError` if the stock isn't currently active on
    the watchlist; propagates `DiscoveryCandidateNotInScanError` (no
    `ScanCandidate` for this scan -- e.g. stale/missing data never scanned) or
    `CandidateNotEligibleError` (the scan already excluded the stock) unchanged
    from `route_discovery_through_pipeline` -- watchlist membership is never a
    special case for either failure mode."""
    if not is_active(session, stock_id):
        raise StockNotOnWatchlistError(
            f"stock {stock_id} is not currently active on the watchlist; nothing to analyze"
        )

    discovery = record_discovery(
        session,
        scan_id=scan_id,
        stock_id=stock_id,
        source=SOURCE_WATCHLIST,
        rationale="active watchlist stock routed for positive analysis",
        discovered_at=as_of_timestamp,
    )

    return route_discovery_through_pipeline(
        session,
        discovery,
        as_of_timestamp=as_of_timestamp,
        entry_price=entry_price,
        target_return=target_return,
        stop_return=stop_return,
    )

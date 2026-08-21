"""EPIC-M1.33: run the platform's discovery -> qualification pipeline as one
scheduled, idempotent, reproducible unit, so new stock candidates keep flowing
into positive-analysis without ever creating a recommendation directly from
discovery itself.

Deliberately composes existing EPICs rather than reimplementing them:
- The "discoverable NSE stock universe" and "generate candidates from measurable
  market signals" scope items are M1.12's `run_daily_candidate_scan`
  (app/scan.py) -- every active `Stock` scanned against real technical features.
- "Deduplicate candidates across scans" is M1.12's own `(scan_date,
  universe_version)` idempotency plus `ScanCandidate`'s `(scan_id, stock_id)`
  uniqueness -- re-running for the same day never creates a second candidate set.
- "Persist discovery timestamp, source, and discovery reason" reuses M1.17's
  `record_discovery` (app/discovery.py) with the new `SOURCE_DAILY_UNIVERSE_SCAN`
  tag, giving internally scanned candidates the same provenance trail externally
  discovered ones already have.
- "Route candidates into the existing positive-analysis pipeline" / "candidates
  enter M1.13/M1.14 qualification flow" is the identical
  `generate_recommendation_for_candidate` (M1.13) and
  `select_recommendations_for_scan` (M1.14) entry points every other discovery
  path in this repo uses -- discovery itself never constructs a `Prediction`.
- "Preserve candidates that fail qualification as backlog/history" falls out for
  free: M1.13's `RecommendationGeneration` rows (qualified or not) and M1.12's
  `ScanCandidate` rows (eligible or not) are never deleted by any code path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .discovery import SOURCE_DAILY_UNIVERSE_SCAN, record_discovery, route_discovery_through_pipeline
from .models import (
    DailyCandidateScan,
    DiscoveryRecord,
    RecommendationGeneration,
    RecommendationSelection,
    ScanCandidate,
)
from .recommendation_selection import DEFAULT_DAILY_LIMIT, MIN_SCORE_FOR_SELECTION, select_recommendations_for_scan
from .scan import UNIVERSE_VERSION, SignalProvider, run_daily_candidate_scan


@dataclass(frozen=True)
class ContinuousDiscoveryResult:
    scan: DailyCandidateScan
    discovery_records: tuple[DiscoveryRecord, ...]
    generations: tuple[RecommendationGeneration, ...]
    selections: tuple[RecommendationSelection, ...]


def record_discovery_for_scan(
    session: Session, scan: DailyCandidateScan, discovered_at: datetime
) -> tuple[DiscoveryRecord, ...]:
    """Give every candidate in `scan` -- eligible or not -- a provenance row.
    Idempotent via `record_discovery`'s own `(scan_id, stock_id, source)`
    uniqueness, so re-running for an already-scanned day changes nothing."""
    candidates = session.scalars(
        select(ScanCandidate).where(ScanCandidate.scan_id == scan.id).order_by(ScanCandidate.stock_id)
    ).all()
    records = [
        record_discovery(
            session,
            scan_id=scan.id,
            stock_id=candidate.stock_id,
            source=SOURCE_DAILY_UNIVERSE_SCAN,
            rationale=(
                f"active NSE stock scanned under universe {scan.universe_version} "
                f"for {scan.scan_date.isoformat()}"
            ),
            discovered_at=discovered_at,
        )
        for candidate in candidates
    ]
    return tuple(records)


def run_scheduled_discovery_scan(
    session: Session,
    scan_date: date,
    signal_provider: SignalProvider,
    *,
    as_of_timestamp: datetime,
    entry_price_for: Callable[[int], Decimal],
    target_return: Decimal,
    stop_return: Decimal,
    universe_version: str = UNIVERSE_VERSION,
    min_score: Decimal = MIN_SCORE_FOR_SELECTION,
    daily_limit: int = DEFAULT_DAILY_LIMIT,
) -> ContinuousDiscoveryResult:
    """The one entry point a scheduler calls once per trading day. Fully
    idempotent end to end: every stage it composes (scan, discovery-provenance,
    generation, selection) is independently idempotent, so calling this twice for
    the same `(scan_date, universe_version)` is a reproducible no-op the second
    time, not a duplicate run (AC: "discovery runs are reproducible for a given
    data snapshot")."""
    summary = run_daily_candidate_scan(session, scan_date, signal_provider, universe_version=universe_version)

    discovery_records = record_discovery_for_scan(session, summary.scan, as_of_timestamp)
    discovery_by_stock_id = {discovery.stock_id: discovery for discovery in discovery_records}

    # Route through `route_discovery_through_pipeline` (not `generate_recommendation_for_candidate`
    # directly) so the daily-scan path links `DiscoveryRecord.recommendation_generation_id` back to
    # its generation exactly like every other discovery source already does -- several analysis
    # modules inner-join on this field and were silently dropping daily-scan-sourced recommendations.
    generations = tuple(
        route_discovery_through_pipeline(
            session,
            discovery_by_stock_id[candidate.stock_id],
            as_of_timestamp=as_of_timestamp,
            entry_price=entry_price_for(candidate.stock_id),
            target_return=target_return,
            stop_return=stop_return,
        )
        for candidate in summary.candidates
        if candidate.eligible
    )

    selections = select_recommendations_for_scan(
        session, summary.scan.id, min_score=min_score, daily_limit=daily_limit
    )

    return ContinuousDiscoveryResult(
        scan=summary.scan,
        discovery_records=discovery_records,
        generations=generations,
        selections=selections,
    )

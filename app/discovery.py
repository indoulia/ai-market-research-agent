"""EPIC-M1.17: let externally (e.g. ChatGPT-assisted) discovered candidate stocks be
routed through exactly the same market-data, prediction, positive-consensus (M1.8),
scoring (M1.9), and horizon (M1.10) evaluation as internally (M1.12 scan) discovered
candidates -- via the identical M1.13 `generate_recommendation_for_candidate` entry
point -- so external discovery can never bypass quantitative qualification. The
discovery rationale is persisted purely as human-readable provenance (source,
timestamp, free-text reasoning) in its own table and is never read by, or passed
into, any consensus/scoring/horizon computation.

A discovered candidate not qualifying under M1.8's consensus gate is recorded by the
routed-through M1.13 generator as `OUTCOME_NOT_QUALIFIED` -- this repo's other
"failed positive consensus" path (app/watchlist.py, M1.7) uses the human-readable
label "NOT MATCHING POSITIVE CONSENSUS" for the same underlying consensus decision,
but that path skips scoring/horizon selection, which this EPIC's scope explicitly
requires; `OUTCOME_NOT_QUALIFIED` is this module's applicable equivalent.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DiscoveryRecord, RecommendationGeneration, ScanCandidate
from .recommendation_generator import generate_recommendation_for_candidate

SOURCE_CHATGPT = "CHATGPT"
# EPIC-M1.33: the source tag for candidates surfaced by the ordinary M1.12 daily
# universe scan, recorded here for the same auditable-provenance reason external
# discovery is -- so "how was this candidate surfaced" has one answer for every
# candidate, not just externally suggested ones.
SOURCE_DAILY_UNIVERSE_SCAN = "DAILY_UNIVERSE_SCAN"


class DiscoveryCandidateNotInScanError(RuntimeError):
    """Raised when the discovered stock has no `ScanCandidate` row in the given
    scan -- there is nothing to route through quantitative evaluation, and no
    recommendation is fabricated to work around that."""


def record_discovery(
    session: Session,
    *,
    scan_id: int,
    stock_id: int,
    rationale: str,
    discovered_at: datetime,
    source: str = SOURCE_CHATGPT,
) -> DiscoveryRecord:
    """Persist discovery provenance only -- source, timestamp, free-text rationale --
    separately from any recommendation evidence. Idempotent: re-recording the same
    `(scan_id, stock_id, source)` returns the existing provenance row unchanged
    rather than duplicating it."""
    existing = session.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.scan_id == scan_id,
            DiscoveryRecord.stock_id == stock_id,
            DiscoveryRecord.source == source,
        )
    )
    if existing is not None:
        return existing

    record = DiscoveryRecord(
        scan_id=scan_id,
        stock_id=stock_id,
        source=source,
        rationale=rationale,
        discovered_at=discovered_at,
        recommendation_generation_id=None,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def route_discovery_through_pipeline(
    session: Session,
    discovery: DiscoveryRecord,
    *,
    as_of_timestamp: datetime,
    entry_price: Decimal,
    target_return: Decimal,
    stop_return: Decimal,
) -> RecommendationGeneration:
    """Routes one discovery record through M1.13's real generator -- the identical
    entry point internally discovered candidates use -- so `discovery.rationale`
    never enters the consensus/scoring/horizon decision at all. Idempotent: a
    discovery already routed returns its existing generation instead of generating
    (or evaluating) again. Raises `DiscoveryCandidateNotInScanError` if the stock
    was never part of the given scan; propagates `CandidateNotEligibleError`
    unchanged if the scan already excluded it (same failure mode as an internally
    discovered candidate, no special-casing for external discovery)."""
    if discovery.recommendation_generation_id is not None:
        return session.get(RecommendationGeneration, discovery.recommendation_generation_id)

    scan_candidate = session.scalar(
        select(ScanCandidate).where(
            ScanCandidate.scan_id == discovery.scan_id,
            ScanCandidate.stock_id == discovery.stock_id,
        )
    )
    if scan_candidate is None:
        raise DiscoveryCandidateNotInScanError(
            f"stock {discovery.stock_id} has no scan_candidate row in scan {discovery.scan_id}; "
            "cannot route an externally discovered candidate through quantitative "
            "evaluation without one"
        )

    generation = generate_recommendation_for_candidate(
        session,
        scan_candidate,
        as_of_timestamp=as_of_timestamp,
        entry_price=entry_price,
        target_return=target_return,
        stop_return=stop_return,
    )

    discovery.recommendation_generation_id = generation.id
    session.commit()
    session.refresh(discovery)
    return generation

"""EPIC-M1.48: capture the evidence that justified a recommendation --
fundamental, news, event, market/sector, and technical/volume -- as an
immutable, per-category snapshot frozen at recommendation time, so users and
future learning can see exactly what the system knew (and didn't know) when
the decision was made.

This repo has real, already-ingested data for only some of these
categories. Following M1.35's own honest-partial-coverage stance (that
module's `DATA_TYPE_FUNDAMENTAL`/`DATA_TYPE_NEWS_EVENT` are named policy
constants with no real ingestion pipeline behind them yet), this module
never fabricates evidence a category doesn't have:

- **Technical/volume**: real, always available for any qualified
  recommendation -- sourced directly from the `ScanCandidate` M1.13 already
  generated it from, freshness checked via M1.35's own
  `check_market_data_freshness`.
- **Market/sector**: real when available -- `Stock.sector` (always present)
  and M1.26's `MarketRegime` for the originating scan ("where available",
  this platform's established pattern since not every scan is classified).
- **News**: real when available -- M1.17's `DiscoveryRecord.rationale` is
  the one genuine qualitative narrative this platform records about why a
  candidate was surfaced; exposed here as "news evidence" rather than
  fabricating a news-article feed that doesn't exist.
- **Fundamental** and **event**: no ingestion pipeline exists for either in
  this repo, so both are always recorded `UNAVAILABLE` -- an honest,
  explicit statement of what the system did not know, never a fabricated
  value (AC: "every recommendation records all required evidence categories
  or an explicit unavailable state").

One immutable row per `(prediction_id, evidence_category)` -- captured once,
never re-derived or overwritten (AC: "historical snapshots cannot be
silently overwritten").
"""
from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import (
    DailyCandidateScan,
    DiscoveryRecord,
    MarketRegime,
    Prediction,
    RecommendationEvidenceItem,
    RecommendationGeneration,
    ScanCandidate,
    Stock,
)
from .refresh_policy import DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT, REASON_MISSING_DATA, check_market_data_freshness, is_data_fresh

EVIDENCE_SNAPSHOT_VERSION = "RES-001"

EVIDENCE_CATEGORY_FUNDAMENTAL = "FUNDAMENTAL"
EVIDENCE_CATEGORY_NEWS = "NEWS"
EVIDENCE_CATEGORY_EVENT = "EVENT"
EVIDENCE_CATEGORY_MARKET_SECTOR = "MARKET_SECTOR"
EVIDENCE_CATEGORY_TECHNICAL_VOLUME = "TECHNICAL_VOLUME"

ALL_EVIDENCE_CATEGORIES = (
    EVIDENCE_CATEGORY_FUNDAMENTAL,
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_CATEGORY_EVENT,
    EVIDENCE_CATEGORY_MARKET_SECTOR,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME,
)

STATUS_AVAILABLE = "AVAILABLE"
STATUS_STALE = "STALE"
STATUS_UNAVAILABLE = "UNAVAILABLE"


class RecommendationEvidenceImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "evidence_category",
    "status",
    "source",
    "reference",
    "evidence_timestamp",
    "is_stale",
    "snapshot_rule_version",
    "captured_at",
    "created_at",
)


@event.listens_for(RecommendationEvidenceItem, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationEvidenceImmutableError(
            f"recommendation evidence item {target.id} field(s) {changed} cannot be modified after creation"
        )


def _unavailable() -> dict:
    return dict(status=STATUS_UNAVAILABLE, source=None, reference=None, evidence_timestamp=None, is_stale=False)


def _fundamental_evidence(session: Session, prediction: Prediction) -> dict:
    return _unavailable()


def _event_evidence(session: Session, prediction: Prediction) -> dict:
    return _unavailable()


def _news_evidence(session: Session, prediction: Prediction) -> dict:
    discovery = session.execute(
        select(DiscoveryRecord)
        .join(RecommendationGeneration, RecommendationGeneration.id == DiscoveryRecord.recommendation_generation_id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalars().first()
    if discovery is None:
        return _unavailable()

    check = is_data_fresh(DATA_TYPE_NEWS_EVENT, discovery.discovered_at, prediction.as_of_timestamp)
    return dict(
        status=STATUS_STALE if not check.is_fresh else STATUS_AVAILABLE,
        source=f"DISCOVERY:{discovery.source}",
        reference=discovery.rationale,
        evidence_timestamp=discovery.discovered_at,
        is_stale=not check.is_fresh,
    )


def _market_sector_evidence(session: Session, prediction: Prediction) -> dict:
    stock = session.get(Stock, prediction.stock_id)
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one_or_none()

    regime = None
    if scan_id is not None:
        regime = session.scalar(select(MarketRegime).where(MarketRegime.scan_id == scan_id))

    parts = []
    if stock is not None and stock.sector is not None:
        parts.append(f"sector={stock.sector}")

    evidence_timestamp = None
    is_stale = False
    if regime is not None:
        parts.append(f"regime={regime.regime}")
        scan = session.get(DailyCandidateScan, scan_id)
        if scan is not None:
            evidence_timestamp = datetime.combine(scan.scan_date, time.min, tzinfo=timezone.utc)
            check = is_data_fresh(DATA_TYPE_MARKET, evidence_timestamp, prediction.as_of_timestamp)
            is_stale = not check.is_fresh

    if not parts:
        return _unavailable()

    return dict(
        status=STATUS_STALE if is_stale else STATUS_AVAILABLE,
        source="STOCK_SECTOR+MARKET_REGIME",
        reference="; ".join(parts),
        evidence_timestamp=evidence_timestamp,
        is_stale=is_stale,
    )


def _technical_volume_evidence(session: Session, prediction: Prediction) -> dict:
    scan_candidate = session.execute(
        select(ScanCandidate)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalars().first()
    if scan_candidate is None:
        return _unavailable()

    check = check_market_data_freshness(session, prediction.stock_id, prediction.as_of_timestamp)
    if check.reason == REASON_MISSING_DATA:
        return _unavailable()

    reference = (
        f"sma20_distance={scan_candidate.sma20_distance}, "
        f"volume_ratio_20d={scan_candidate.volume_ratio_20d}, "
        f"atr_percent={scan_candidate.atr_percent}"
    )
    return dict(
        status=STATUS_STALE if not check.is_fresh else STATUS_AVAILABLE,
        source="SCAN_CANDIDATE_TECHNICALS",
        reference=reference,
        evidence_timestamp=check.source_timestamp,
        is_stale=not check.is_fresh,
    )


_CATEGORY_BUILDERS = {
    EVIDENCE_CATEGORY_FUNDAMENTAL: _fundamental_evidence,
    EVIDENCE_CATEGORY_NEWS: _news_evidence,
    EVIDENCE_CATEGORY_EVENT: _event_evidence,
    EVIDENCE_CATEGORY_MARKET_SECTOR: _market_sector_evidence,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME: _technical_volume_evidence,
}


def get_evidence_snapshot(session: Session, prediction_id: int) -> tuple[RecommendationEvidenceItem, ...]:
    """Retrieve the complete recommendation evidence snapshot (AC: "UI/API
    can retrieve the complete recommendation evidence snapshot"), ordered
    consistently by category."""
    items = {
        item.evidence_category: item
        for item in session.scalars(
            select(RecommendationEvidenceItem).where(RecommendationEvidenceItem.prediction_id == prediction_id)
        ).all()
    }
    return tuple(items[c] for c in ALL_EVIDENCE_CATEGORIES if c in items)


def capture_evidence_snapshot(
    session: Session, prediction: Prediction, *, captured_at: datetime
) -> tuple[RecommendationEvidenceItem, ...]:
    """Captures all five evidence categories for `prediction`, once.
    Idempotent: a prediction already fully snapshotted returns its original
    rows unchanged, never re-derived, even if the underlying evidence (e.g.
    a stock's sector) has since changed (AC: "historical snapshots cannot
    be silently overwritten")."""
    existing = get_evidence_snapshot(session, prediction.id)
    existing_categories = {item.evidence_category for item in existing}
    if existing_categories == set(ALL_EVIDENCE_CATEGORIES):
        return existing

    new_items = []
    for category in ALL_EVIDENCE_CATEGORIES:
        if category in existing_categories:
            continue
        data = _CATEGORY_BUILDERS[category](session, prediction)
        item = RecommendationEvidenceItem(
            prediction_id=prediction.id,
            evidence_category=category,
            status=data["status"],
            source=data["source"],
            reference=data["reference"],
            evidence_timestamp=data["evidence_timestamp"],
            is_stale=data["is_stale"],
            snapshot_rule_version=EVIDENCE_SNAPSHOT_VERSION,
            captured_at=captured_at,
        )
        session.add(item)
        new_items.append(item)

    session.commit()
    for item in new_items:
        session.refresh(item)

    return get_evidence_snapshot(session, prediction.id)

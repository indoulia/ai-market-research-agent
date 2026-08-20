"""EPIC-M1.34: make discovery systematic across market-cap, sector, industry, and
liquidity dimensions by snapshotting each discovered candidate's segment
membership at the moment of discovery -- never re-derived later, so a stock's
`sector`/`market_cap` changing afterward can't retroactively rewrite what segment
a historical discovery belonged to at the time.

Deliberately does not change what gets discovered or how it qualifies: this EPIC's
non-goals rule out changing recommendation qualification rules, and the module
below only classifies and measures, it never filters `app/continuous_discovery.py`'s
candidate set or M1.13's consensus gate.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import DiscoveryRecord, DiscoverySegment, ScanCandidate, Stock

SEGMENTATION_VERSION = "SEG-001"

BUCKET_UNCLASSIFIED = "UNCLASSIFIED"

# Fixed product/policy constants (INR crore), bumped via SEGMENTATION_VERSION
# whenever changed. Thresholds mirror the conventional NSE large/mid/small-cap
# split; ordered highest-first for a first-match-wins scan.
MARKET_CAP_BUCKET_THRESHOLDS = (
    (Decimal("20000"), "LARGE_CAP"),
    (Decimal("5000"), "MID_CAP"),
    (Decimal("0"), "SMALL_CAP"),
)

# Fixed product/policy constants on the same volume_ratio_20d signal M1.8's
# consensus gate uses as a pass/fail floor (MIN_VOLUME_RATIO_20D=0.75) -- these
# thresholds instead describe a *segment*, not a qualification boundary, so they
# are intentionally distinct constants versioned independently.
LIQUIDITY_BUCKET_THRESHOLDS = (
    (Decimal("1.5"), "HIGH"),
    (Decimal("0.75"), "NORMAL"),
    (Decimal("0"), "LOW"),
)

# Scope item "prevent over-concentration in a single segment": a fixed detection
# threshold, not an enforced filter -- flagging is this EPIC's job; deciding to
# drop/limit candidates because of it would be a qualification-rule change,
# which is explicitly out of scope (non-goal).
DEFAULT_MAX_SEGMENT_SHARE = Decimal("0.60")


class DiscoverySegmentImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "discovery_record_id",
    "market_cap_bucket",
    "sector",
    "industry",
    "liquidity_bucket",
    "segmentation_rule_version",
    "created_at",
)


@event.listens_for(DiscoverySegment, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise DiscoverySegmentImmutableError(
            f"discovery segment {target.id} field(s) {changed} cannot be modified after creation"
        )


def classify_market_cap_bucket(market_cap: Decimal | None) -> str:
    if market_cap is None:
        return BUCKET_UNCLASSIFIED
    for threshold, bucket in MARKET_CAP_BUCKET_THRESHOLDS:
        if market_cap >= threshold:
            return bucket
    return BUCKET_UNCLASSIFIED


def classify_liquidity_bucket(volume_ratio_20d: Decimal | None) -> str:
    if volume_ratio_20d is None:
        return BUCKET_UNCLASSIFIED
    for threshold, bucket in LIQUIDITY_BUCKET_THRESHOLDS:
        if volume_ratio_20d >= threshold:
            return bucket
    return BUCKET_UNCLASSIFIED


def record_segment_for_discovery(
    session: Session, discovery: DiscoveryRecord, stock: Stock, scan_candidate: ScanCandidate | None
) -> DiscoverySegment:
    """Snapshot one discovery's segment membership. Idempotent by
    `discovery_record_id` uniqueness -- a discovery already segmented returns its
    original snapshot unchanged rather than re-deriving it from (possibly since
    updated) `Stock`/`ScanCandidate` fields."""
    existing = session.scalar(
        select(DiscoverySegment).where(DiscoverySegment.discovery_record_id == discovery.id)
    )
    if existing is not None:
        return existing

    volume_ratio_20d = scan_candidate.volume_ratio_20d if scan_candidate is not None else None
    segment = DiscoverySegment(
        discovery_record_id=discovery.id,
        market_cap_bucket=classify_market_cap_bucket(stock.market_cap),
        sector=stock.sector or BUCKET_UNCLASSIFIED,
        industry=stock.industry or BUCKET_UNCLASSIFIED,
        liquidity_bucket=classify_liquidity_bucket(volume_ratio_20d),
        segmentation_rule_version=SEGMENTATION_VERSION,
    )
    session.add(segment)
    session.commit()
    session.refresh(segment)
    return segment


def record_segments_for_scan(session: Session, scan_id: int) -> tuple[DiscoverySegment, ...]:
    """Segments every `DiscoveryRecord` already persisted for `scan_id` (e.g. by
    M1.33's `record_discovery_for_scan`). Idempotent for the same reason
    `record_segment_for_discovery` is."""
    rows = session.execute(
        select(DiscoveryRecord, Stock, ScanCandidate)
        .join(Stock, Stock.id == DiscoveryRecord.stock_id)
        .join(
            ScanCandidate,
            (ScanCandidate.scan_id == DiscoveryRecord.scan_id) & (ScanCandidate.stock_id == DiscoveryRecord.stock_id),
            isouter=True,
        )
        .where(DiscoveryRecord.scan_id == scan_id)
        .order_by(DiscoveryRecord.id)
    ).all()
    return tuple(
        record_segment_for_discovery(session, discovery, stock, scan_candidate)
        for discovery, stock, scan_candidate in rows
    )


@dataclass(frozen=True)
class SegmentCoverage:
    by_market_cap_bucket: dict
    by_sector: dict
    by_industry: dict
    by_liquidity_bucket: dict
    total: int


def segment_coverage_for_scan(session: Session, scan_id: int) -> SegmentCoverage:
    """Measurable per-dimension candidate counts for one discovery run (scope
    item "segment coverage is measurable per discovery run")."""
    segments = session.scalars(
        select(DiscoverySegment)
        .join(DiscoveryRecord, DiscoveryRecord.id == DiscoverySegment.discovery_record_id)
        .where(DiscoveryRecord.scan_id == scan_id)
    ).all()
    return SegmentCoverage(
        by_market_cap_bucket=dict(Counter(s.market_cap_bucket for s in segments)),
        by_sector=dict(Counter(s.sector for s in segments)),
        by_industry=dict(Counter(s.industry for s in segments)),
        by_liquidity_bucket=dict(Counter(s.liquidity_bucket for s in segments)),
        total=len(segments),
    )


def over_concentrated_segments(
    coverage_by_key: dict, total: int, *, max_share: Decimal = DEFAULT_MAX_SEGMENT_SHARE
) -> tuple[str, ...]:
    """Flags which keys of a single coverage dimension (e.g.
    `SegmentCoverage.by_sector`) exceed `max_share` of `total` -- detection only,
    per this module's docstring; nothing here removes or excludes a candidate."""
    if total == 0:
        return ()
    return tuple(
        key for key, count in coverage_by_key.items() if Decimal(count) / Decimal(total) > max_share
    )


def discovery_records_in_segment(
    session: Session,
    scan_id: int,
    *,
    market_cap_bucket: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    liquidity_bucket: str | None = None,
) -> tuple[DiscoveryRecord, ...]:
    """Lets a caller operate on one discovery run's results independently by
    segment (scope item "discovery can run independently by segment") without
    needing a separate scan per segment -- the underlying M1.12 scan already
    covers the whole universe in one pass; this filters that single pass's
    already-persisted, already-segmented results."""
    query = (
        select(DiscoveryRecord)
        .join(DiscoverySegment, DiscoverySegment.discovery_record_id == DiscoveryRecord.id)
        .where(DiscoveryRecord.scan_id == scan_id)
    )
    if market_cap_bucket is not None:
        query = query.where(DiscoverySegment.market_cap_bucket == market_cap_bucket)
    if sector is not None:
        query = query.where(DiscoverySegment.sector == sector)
    if industry is not None:
        query = query.where(DiscoverySegment.industry == industry)
    if liquidity_bucket is not None:
        query = query.where(DiscoverySegment.liquidity_bucket == liquidity_bucket)
    return tuple(session.scalars(query.order_by(DiscoveryRecord.id)).all())

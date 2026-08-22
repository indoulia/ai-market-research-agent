"""Query services backing GET /api/v1/system/{health,providers,
data-freshness,events} (EPIC-M3.11).

Reconciles with M1.93 (`app.provider_quality`), M1.114 (`app.
provider_outage_tracker`) and M1.126 (`app.information_latency`) by
composing their already-tested, already-persisted signals rather than
recomputing provider reliability, outage severity or latency degradation
a second time. This module's only genuinely new logic is the thin
API-shaping layer: per-(data_type, provider_id) last-success-timestamp and
average-ingestion-latency lookups (M1.93's own report doesn't carry
those), and merging outage/closure/latency-degradation history into one
time-ordered events feed for `/system/events`.

Honest, named gap: there is no live, credentialed provider registry wired
into the API process (concrete adapters need real API keys/config this
layer never holds), so `compute_provider_quality_report` is always called
with no live `providers` -- `health_statuses` is always empty and
`status` per provider reflects only the historical `DataFetchAttempt`
verdict (`OK`/`WEAK`/`INSUFFICIENT_SAMPLE`), never a live ping. This is
the same posture M1.93's own docstring documents for callers "that only
want historical metrics".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.discovery_effectiveness import VERDICT_WEAK
from app.information_latency import VERDICT_DEGRADED as LATENCY_VERDICT_DEGRADED
from app.models import DataFetchAttempt, LatencyDegradationReport, MarketUnexpectedClosure, ProviderOutageSnapshot
from app.provider_outage_tracker import SEVERITY_NONE, SEVERITY_PARTIAL, SEVERITY_TOTAL, get_latest_outage_snapshot
from app.provider_quality import compute_provider_quality_report
from app.refresh_policy import FRESHNESS_POLICY
from app.schedule_orchestration import classify_session

from ..pagination import decode_offset_cursor, encode_offset_cursor
from ..schemas.system import (
    SYSTEM_STATUS_DEGRADED,
    SYSTEM_STATUS_OK,
    SYSTEM_STATUS_OUTAGE,
    DataFreshnessItem,
    Freshness,
    ProviderStatus,
    SystemEventItem,
    SystemHealthResponse,
)
from ..versioning import API_VERSION

SYSTEM_HEALTH_VERSION = "SYH-001"

EVENT_TYPE_PROVIDER_OUTAGE = "PROVIDER_OUTAGE"
EVENT_TYPE_UNEXPECTED_CLOSURE = "MARKET_UNEXPECTED_CLOSURE"
EVENT_TYPE_LATENCY_DEGRADATION = "LATENCY_DEGRADATION"

EVENT_SEVERITY_INFO = "INFO"
EVENT_SEVERITY_WARNING = "WARNING"


def _as_aware_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on DateTime(timezone=True) round-trip (same class
    # of bug already fixed in api/services/tracking.py and dashboard.py);
    # normalize before any Python-side comparison/sort across sources.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _freshness(last_success_at: datetime | None, data_type: str, computed_at: datetime) -> Freshness:
    threshold_seconds = int(FRESHNESS_POLICY[data_type].total_seconds())
    if last_success_at is None:
        return Freshness(ageSeconds=None, thresholdSeconds=threshold_seconds, isFresh=False)
    age_seconds = int((computed_at - _as_aware_utc(last_success_at)).total_seconds())
    return Freshness(ageSeconds=age_seconds, thresholdSeconds=threshold_seconds, isFresh=age_seconds <= threshold_seconds)


def _provider_activity(session: Session) -> dict[tuple[str, str], dict]:
    """Per-`(data_type, provider_id)` last successful fetch and that same
    fetch's ingestion latency (`requested_at - source_timestamp`, in
    seconds) -- the two provider-response fields M1.93's own
    `ProviderQualityMetric` doesn't carry.

    `latencyMs` (bug found during live Rancher/k3s deployment validation)
    intentionally reflects only the MOST RECENT successful fetch --
    the same row `last_success_at` is derived from -- rather than an
    average of `requested_at - source_timestamp` across every row ever
    recorded. An unbounded average is dominated by one-time historical
    backfills (e.g. an 8-month candle backfill where every row's
    `requested_at` is ~now but `source_timestamp` ranges back months),
    which produced a "latency" of ~44 hours that had nothing to do with
    the provider's current operational health -- exactly the "market
    condition vs. information-system degradation" distinction this field
    exists to support. "How fresh is our latest update" (this) and
    "what's our success/failure rate over history" (`qualityScore`/
    `failureRate`, from `compute_provider_quality_report`) are
    deliberately different metrics with different time horizons; only
    this point-in-time latency reading is fixed here."""
    rows = session.execute(
        select(
            DataFetchAttempt.data_type,
            DataFetchAttempt.provider_id,
            DataFetchAttempt.requested_at,
            DataFetchAttempt.source_timestamp,
        ).where(DataFetchAttempt.provider_id.is_not(None), DataFetchAttempt.success.is_(True))
    ).all()

    activity: dict[tuple[str, str], dict] = {}
    for data_type, provider_id, requested_at, source_timestamp in rows:
        key = (data_type, provider_id)
        bucket = activity.setdefault(key, {"last_success_at": None, "last_latency_seconds": None})
        requested_at = _as_aware_utc(requested_at)
        if bucket["last_success_at"] is None or requested_at > bucket["last_success_at"]:
            bucket["last_success_at"] = requested_at
            bucket["last_latency_seconds"] = (
                (requested_at - _as_aware_utc(source_timestamp)).total_seconds()
                if source_timestamp is not None
                else None
            )
    return activity


def get_provider_status(session: Session, *, computed_at: datetime) -> list[ProviderStatus]:
    report = compute_provider_quality_report(session, computed_at=computed_at)
    activity = _provider_activity(session)
    outage_by_data_type = {data_type: get_latest_outage_snapshot(session, data_type) for data_type in FRESHNESS_POLICY}

    items: list[ProviderStatus] = []
    for metric in report.by_provider:
        bucket = activity.get((metric.data_type, metric.provider_id), {})
        last_success_at = bucket.get("last_success_at")
        last_latency_seconds = bucket.get("last_latency_seconds")
        latency_ms = int(last_latency_seconds * 1000) if last_latency_seconds is not None else None

        snapshot = outage_by_data_type.get(metric.data_type)
        fallback_active = bool(snapshot is not None and metric.provider_id in (snapshot.degraded_provider_ids or []))

        failure_rate = (Decimal(1) - metric.success_rate) if metric.success_rate is not None else None

        items.append(
            ProviderStatus(
                providerId=metric.provider_id,
                capability=metric.data_type,
                status=metric.verdict,
                lastSuccessAt=last_success_at,
                latencyMs=latency_ms,
                freshness=_freshness(last_success_at, metric.data_type, computed_at),
                failureRate=failure_rate,
                fallbackActive=fallback_active,
                qualityScore=metric.success_rate,
            )
        )
    return items


def get_data_freshness(session: Session, *, computed_at: datetime) -> list[DataFreshnessItem]:
    items: list[DataFreshnessItem] = []
    for data_type in FRESHNESS_POLICY:
        last_success_at = session.scalar(
            select(func.max(DataFetchAttempt.requested_at)).where(
                DataFetchAttempt.data_type == data_type, DataFetchAttempt.success.is_(True),
            )
        )
        last_success_at = _as_aware_utc(last_success_at) if last_success_at is not None else None
        freshness = _freshness(last_success_at, data_type, computed_at)
        items.append(
            DataFreshnessItem(
                capability=data_type,
                lastSuccessAt=last_success_at,
                ageSeconds=freshness.ageSeconds,
                thresholdSeconds=freshness.thresholdSeconds,
                isFresh=freshness.isFresh,
            )
        )
    return items


def get_system_health(session: Session, *, computed_at: datetime) -> SystemHealthResponse:
    try:
        session.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # pragma: no cover - depends on infra availability
        database_ok = False

    providers = get_provider_status(session, computed_at=computed_at)
    provider_status_counts: dict[str, int] = {}
    for provider in providers:
        provider_status_counts[provider.status] = provider_status_counts.get(provider.status, 0) + 1

    latest_snapshots = [get_latest_outage_snapshot(session, data_type) for data_type in FRESHNESS_POLICY]
    active_outage_count = sum(1 for s in latest_snapshots if s is not None and s.severity != SEVERITY_NONE)
    has_total_outage = any(s is not None and s.severity == SEVERITY_TOTAL for s in latest_snapshots)
    has_partial_outage = any(s is not None and s.severity == SEVERITY_PARTIAL for s in latest_snapshots)
    has_weak_provider = any(p.status == VERDICT_WEAK for p in providers)

    if not database_ok or has_total_outage:
        status = SYSTEM_STATUS_OUTAGE
    elif has_partial_outage or has_weak_provider:
        status = SYSTEM_STATUS_DEGRADED
    else:
        status = SYSTEM_STATUS_OK

    # NSE weekday/session-window classification (M1.118's own
    # `classify_session`), with no holiday calendar applied -- there is no
    # `MarketCalendarVersion` seeded anywhere in this platform's production
    # data (M1.121's registry starts empty), the same honest gap
    # `api/services/market.py::get_market_summary` already documents for
    # `marketStatus`. Real weekday/time-of-day session awareness is still
    # genuinely more informative than a permanent "UNKNOWN".
    market_session = classify_session(computed_at)

    return SystemHealthResponse(
        status=status,
        checkedAt=computed_at,
        apiVersion=API_VERSION,
        databaseOk=database_ok,
        providerStatusCounts=provider_status_counts,
        activeOutageCount=active_outage_count,
        marketSession=market_session,
    )


def _outage_events(session: Session) -> list[SystemEventItem]:
    rows = session.scalars(
        select(ProviderOutageSnapshot)
        .where(ProviderOutageSnapshot.severity != SEVERITY_NONE)
        .order_by(ProviderOutageSnapshot.evaluated_at.desc())
    ).all()
    return [
        SystemEventItem(
            id=f"outage-{row.id}",
            type=EVENT_TYPE_PROVIDER_OUTAGE,
            severity=row.severity,
            capability=row.data_type,
            exchange=None,
            description=(
                f"{row.degraded_provider_count}/{row.total_registered_providers} provider(s) degraded for "
                f"{row.data_type}: {', '.join(row.degraded_provider_ids) if row.degraded_provider_ids else 'none named'}"
            ),
            occurredAt=_as_aware_utc(row.evaluated_at),
        )
        for row in rows
    ]


def _closure_events(session: Session) -> list[SystemEventItem]:
    rows = session.scalars(select(MarketUnexpectedClosure).order_by(MarketUnexpectedClosure.recorded_at.desc())).all()
    return [
        SystemEventItem(
            id=f"closure-{row.id}",
            type=EVENT_TYPE_UNEXPECTED_CLOSURE,
            severity=EVENT_SEVERITY_INFO,
            capability=None,
            exchange=row.exchange,
            description=f"Unexpected closure on {row.closure_date.isoformat()}: {row.reason}",
            occurredAt=_as_aware_utc(row.recorded_at),
        )
        for row in rows
    ]


def _latency_degradation_events(session: Session) -> list[SystemEventItem]:
    rows = session.scalars(
        select(LatencyDegradationReport)
        .where(LatencyDegradationReport.verdict == LATENCY_VERDICT_DEGRADED)
        .order_by(LatencyDegradationReport.computed_at.desc())
    ).all()
    items = []
    for row in rows:
        if row.degradation_ratio is not None:
            description = (
                f"Ingestion latency for {row.data_type} degraded {row.degradation_ratio:.0%} "
                f"vs. baseline ({row.window_label})"
            )
        else:  # pragma: no cover - degradation_ratio is always set for a DEGRADED verdict
            description = f"Ingestion latency degraded for {row.data_type} ({row.window_label})"
        items.append(
            SystemEventItem(
                id=f"latency-{row.id}",
                type=EVENT_TYPE_LATENCY_DEGRADATION,
                severity=EVENT_SEVERITY_WARNING,
                capability=row.data_type,
                exchange=None,
                description=description,
                occurredAt=_as_aware_utc(row.computed_at),
            )
        )
    return items


@dataclass
class SystemEventsPage:
    items: list[SystemEventItem]
    next_cursor: str | None


def get_system_events(session: Session, *, page_size: int, cursor: str | None) -> SystemEventsPage:
    """Merges M1.114's outage-severity history, M1.121's unexpected-closure
    log and M1.126's latency-degradation reports into one time-ordered
    incident feed (AC: "system incident/history drill-down"). Offset-cursor
    paginated over this merged, in-memory-sorted list -- appropriate here
    per `api/pagination.py`'s own guidance, since every source table is a
    periodic/administrative snapshot log, not a high-volume live stream."""
    all_events = sorted(
        _outage_events(session) + _closure_events(session) + _latency_degradation_events(session),
        key=lambda e: e.occurredAt,
        reverse=True,
    )
    offset = decode_offset_cursor(cursor) if cursor else 0
    page_items = all_events[offset : offset + page_size]
    next_offset = offset + page_size
    next_cursor = encode_offset_cursor(next_offset) if next_offset < len(all_events) else None
    return SystemEventsPage(items=page_items, next_cursor=next_cursor)

"""EPIC-M1.64: measure the freshness, completeness, availability, and
historical reliability of every external information source used by
recommendations, and expose an explicit evidence-quality status downstream
confidence calculations can consult -- never silently granting full trust
to low-quality evidence.

Composes rather than duplicates: M1.35's `DataFetchAttempt` (freshness/
latency/success per data type) and M1.48's `RecommendationEvidenceItem`
(availability/staleness per evidence category, across every recommendation
that has been snapshotted). Reuses M1.28's `VERDICT_OK`/`VERDICT_WEAK`/
`VERDICT_INSUFFICIENT_SAMPLE` vocabulary and M1.16's
`MIN_SAMPLE_SIZE_FOR_COMPARISON` -- the same "is this evidence reliable"
question, applied to data sources instead of discovery sources.

Read-only and deterministic; writes nothing anywhere. "Expose ... to
downstream confidence calculations" (scope) means producing a queryable
`EvidenceQualityStatus` per data type/category that a future confidence
calculation *could* consult -- this module does not itself modify M1.49/
M1.50's calibration or quality logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .discovery_effectiveness import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK
from .models import DataFetchAttempt, RecommendationEvidenceItem
from .refresh_policy import FRESHNESS_POLICY
from .evidence_snapshot import STATUS_AVAILABLE, STATUS_STALE, STATUS_UNAVAILABLE
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

DATA_SOURCE_RELIABILITY_VERSION = "DSR-001"

# A data source's success rate must clear this to be called reliable, given
# sufficient sample. Fixed, documented, versioned -- not learned or fitted.
RELIABILITY_SUCCESS_THRESHOLD = Decimal("0.90")

# An evidence category's availability rate below this is too thin to trust
# fully, even if every individual fetch that did happen succeeded.
COVERAGE_TRUST_THRESHOLD = Decimal("0.50")


@dataclass(frozen=True)
class SourceReliabilityMetric:
    data_type: str
    total_attempts: int
    successful_attempts: int
    success_rate: Decimal | None
    average_latency_seconds: Decimal | None
    verdict: str


@dataclass(frozen=True)
class EvidenceCoverageMetric:
    evidence_category: str
    total_items: int
    available_count: int
    stale_count: int
    unavailable_count: int
    coverage_rate: Decimal | None


@dataclass(frozen=True)
class EvidenceQualityStatus:
    key: str
    trusted: bool
    reason: str


@dataclass(frozen=True)
class DataSourceReliabilityReport:
    version: str
    by_data_type: tuple[SourceReliabilityMetric, ...]
    by_evidence_category: tuple[EvidenceCoverageMetric, ...]
    quality_statuses: tuple[EvidenceQualityStatus, ...]


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _reliability_verdict(sample_count: int, success_rate: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or success_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if success_rate < RELIABILITY_SUCCESS_THRESHOLD:
        return VERDICT_WEAK
    return VERDICT_OK


def _source_reliability(session: Session) -> tuple[SourceReliabilityMetric, ...]:
    """Freshness/latency/completeness per external data type (scope:
    "track source freshness and latency"; "track completeness and
    failures"), reusing M1.35's own `DataFetchAttempt` log unchanged."""
    metrics = []
    for data_type in sorted(FRESHNESS_POLICY):
        attempts = session.scalars(
            select(DataFetchAttempt).where(DataFetchAttempt.data_type == data_type)
        ).all()
        total = len(attempts)
        successful = [a for a in attempts if a.success]
        success_rate = _rate(len(successful), total)

        latencies = [
            (a.requested_at.replace(tzinfo=None) - a.source_timestamp.replace(tzinfo=None)).total_seconds()
            for a in successful
            if a.source_timestamp is not None
        ]
        average_latency = (
            Decimal(sum(latencies)) / Decimal(len(latencies)) if latencies else None
        )

        metrics.append(
            SourceReliabilityMetric(
                data_type=data_type,
                total_attempts=total,
                successful_attempts=len(successful),
                success_rate=success_rate,
                average_latency_seconds=average_latency,
                verdict=_reliability_verdict(total, success_rate),
            )
        )
    return tuple(metrics)


def _evidence_coverage(session: Session) -> tuple[EvidenceCoverageMetric, ...]:
    """Coverage per evidence category (scope: "track source coverage")
    across every recommendation snapshotted by M1.48."""
    rows = session.execute(
        select(RecommendationEvidenceItem.evidence_category, RecommendationEvidenceItem.status)
    ).all()

    by_category: dict[str, dict[str, int]] = {}
    for category, status in rows:
        bucket = by_category.setdefault(category, {STATUS_AVAILABLE: 0, STATUS_STALE: 0, STATUS_UNAVAILABLE: 0})
        bucket[status] = bucket.get(status, 0) + 1

    metrics = []
    for category in sorted(by_category):
        bucket = by_category[category]
        total = sum(bucket.values())
        metrics.append(
            EvidenceCoverageMetric(
                evidence_category=category,
                total_items=total,
                available_count=bucket.get(STATUS_AVAILABLE, 0),
                stale_count=bucket.get(STATUS_STALE, 0),
                unavailable_count=bucket.get(STATUS_UNAVAILABLE, 0),
                coverage_rate=_rate(bucket.get(STATUS_AVAILABLE, 0), total),
            )
        )
    return tuple(metrics)


def _quality_statuses(
    by_data_type: tuple[SourceReliabilityMetric, ...], by_evidence_category: tuple[EvidenceCoverageMetric, ...]
) -> tuple[EvidenceQualityStatus, ...]:
    """Never silently grants full trust (AC): the default for insufficient
    or weak evidence is always `trusted=False`, with an explicit reason."""
    statuses = []
    for metric in by_data_type:
        if metric.verdict == VERDICT_OK:
            statuses.append(EvidenceQualityStatus(key=metric.data_type, trusted=True, reason="reliable success rate with sufficient sample"))
        elif metric.verdict == VERDICT_WEAK:
            statuses.append(EvidenceQualityStatus(key=metric.data_type, trusted=False, reason=f"success rate {metric.success_rate} below reliability threshold"))
        else:
            statuses.append(EvidenceQualityStatus(key=metric.data_type, trusted=False, reason="insufficient fetch-attempt sample to assess reliability"))

    for metric in by_evidence_category:
        if metric.coverage_rate is None:
            statuses.append(EvidenceQualityStatus(key=metric.evidence_category, trusted=False, reason="no evidence items recorded for this category"))
        elif metric.coverage_rate < COVERAGE_TRUST_THRESHOLD:
            statuses.append(EvidenceQualityStatus(key=metric.evidence_category, trusted=False, reason=f"coverage rate {metric.coverage_rate} below trust threshold"))
        else:
            statuses.append(EvidenceQualityStatus(key=metric.evidence_category, trusted=True, reason="sufficient coverage"))

    return tuple(statuses)


def compute_data_source_reliability_report(session: Session) -> DataSourceReliabilityReport:
    """Deterministic aggregate over M1.35/M1.48's own already-recorded data
    (AC: "reliability metrics are reproducible") -- writes nothing."""
    by_data_type = _source_reliability(session)
    by_evidence_category = _evidence_coverage(session)
    return DataSourceReliabilityReport(
        version=DATA_SOURCE_RELIABILITY_VERSION,
        by_data_type=by_data_type,
        by_evidence_category=by_evidence_category,
        quality_statuses=_quality_statuses(by_data_type, by_evidence_category),
    )

"""EPIC-M1.126: measure whether MRA receives, validates and acts on
external information quickly enough for the prediction horizon it is
supporting, and prevent stale information from silently continuing to
support an active prediction.

**Honest scope on the four named timestamps**: this platform's only
provider (Yahoo Finance, research/prototyping only per the product
constraints) exposes a source-event/as-of timestamp and the moment MRA
fetched it (`DataFetchAttempt.source_timestamp`/`requested_at`, from
M1.35), but not a distinct "provider-receipt" timestamp -- there is no
real gap between "the provider received it" and "we fetched it" to
measure separately. `_ingestion_latency` is therefore the one real,
measurable stage (`requested_at - source_timestamp`); "provider latency"
in the EPIC's own scope collapses into it rather than being fabricated
as a second number this platform cannot actually observe.

**Decision latency is this EPIC's own, genuinely new measurement**: the
gap between when a piece of evidence (M1.48's `RecommendationEvidenceItem
.evidence_timestamp`) became available and when the prediction that used
it was actually made (`Prediction.as_of_timestamp`) -- nothing in this
platform currently records how much of a horizon's own runway was
already consumed by the time a prediction reacted to its own evidence.

**Freshness SLA differs by horizon (AC)**: `horizon_adjusted_threshold`
tightens M1.35's own `FRESHNESS_POLICY` threshold by a fixed, documented
multiplier for shorter horizons -- a 1-day-horizon prediction cannot
tolerate the same staleness a 7-day-horizon one can, so the same raw
staleness number is judged against a different bar depending on
`horizon_days`.

**Stale data cannot silently support a prediction (AC)**: `
assess_information_latency` is a read-only, propose-only signal --
`suppress_eligibility=True` has no write path to `Prediction` or any
qualification/gate table. Wiring it into an actual eligibility gate
(alongside M1.74's own evidence-quality gate) is left as explicit future
work for whichever EPIC formally adopts this one as a dependency, the
same posture M1.112's `assess_assumption_decay` took before this
session's own M1.119 became the first consumer of that signal.

**Historical freshness values are immutable (AC)**: `
InformationLatencyAssessment` rows are idempotent by
`(prediction_id, evaluated_at)`; `measure_latency_degradation` always
computes and persists a fresh, independent report, mirroring M1.99's
own `RankingEffectivenessReport` posture, never mutating a prior one.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence_snapshot import (
    EVIDENCE_CATEGORY_EVENT,
    EVIDENCE_CATEGORY_FUNDAMENTAL,
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME,
    STATUS_AVAILABLE,
    get_evidence_snapshot,
)
from .models import DataFetchAttempt, InformationLatencyAssessment, LatencyDegradationReport, Prediction
from .out_of_sample_validation import EvaluationWindow
from .refresh_policy import DATA_TYPE_FUNDAMENTAL, DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT, FRESHNESS_POLICY
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

LATENCY_RULE_VERSION = "ILT-001"
DEGRADATION_RULE_VERSION = "LDR-001"

# Categories this EPIC can actually measure decision latency for -- M1.35's
# own freshness policy has no real per-source timestamp for
# MARKET_SECTOR (a static classification, no "fetch" event), matching the
# same honest exclusion M1.112 already documents.
_CATEGORY_TO_DATA_TYPE = {
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME: DATA_TYPE_MARKET,
    EVIDENCE_CATEGORY_FUNDAMENTAL: DATA_TYPE_FUNDAMENTAL,
    EVIDENCE_CATEGORY_NEWS: DATA_TYPE_NEWS_EVENT,
    EVIDENCE_CATEGORY_EVENT: DATA_TYPE_NEWS_EVENT,
}

# Fixed, documented, versioned SLA tiers by horizon -- shorter horizons
# tolerate proportionally less staleness. Not learned or fitted.
_HORIZON_SLA_TIERS: tuple[tuple[int, Decimal], ...] = (
    (1, Decimal("0.5")),
    (3, Decimal("0.75")),
)
_DEFAULT_SLA_MULTIPLIER = Decimal("1.0")

REASON_STALE_CATEGORY = "STALE_CATEGORY"
REASON_MISSING_TIMESTAMP = "MISSING_EVIDENCE_TIMESTAMP"

VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
VERDICT_DEGRADED = "DEGRADED"
VERDICT_IMPROVED = "IMPROVED"
VERDICT_STABLE = "STABLE"


def sla_multiplier_for_horizon(horizon_days: int) -> Decimal:
    for max_days, multiplier in _HORIZON_SLA_TIERS:
        if horizon_days <= max_days:
            return multiplier
    return _DEFAULT_SLA_MULTIPLIER


def horizon_adjusted_threshold(base_threshold: timedelta, horizon_days: int) -> timedelta:
    multiplier = sla_multiplier_for_horizon(horizon_days)
    return base_threshold * float(multiplier)


def assess_information_latency(session: Session, prediction: Prediction, *, evaluated_at: datetime) -> InformationLatencyAssessment:
    """Idempotent by `(prediction_id, evaluated_at)`."""
    existing = session.scalar(
        select(InformationLatencyAssessment).where(
            InformationLatencyAssessment.prediction_id == prediction.id,
            InformationLatencyAssessment.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    multiplier = sla_multiplier_for_horizon(prediction.horizon_days)
    items = get_evidence_snapshot(session, prediction.id)

    category_latency_seconds: dict[str, float] = {}
    sla_violations: list[str] = []
    reasons: list[str] = []

    for item in items:
        if item.status != STATUS_AVAILABLE or item.evidence_category not in _CATEGORY_TO_DATA_TYPE:
            continue
        if item.evidence_timestamp is None:
            reasons.append(f"{item.evidence_category}:{REASON_MISSING_TIMESTAMP}")
            sla_violations.append(item.evidence_category)
            continue

        decision_latency = prediction.as_of_timestamp.replace(tzinfo=None) - item.evidence_timestamp.replace(tzinfo=None)
        category_latency_seconds[item.evidence_category] = decision_latency.total_seconds()

        data_type = _CATEGORY_TO_DATA_TYPE[item.evidence_category]
        threshold = horizon_adjusted_threshold(FRESHNESS_POLICY[data_type], prediction.horizon_days)
        if decision_latency > threshold:
            sla_violations.append(item.evidence_category)
            reasons.append(f"{item.evidence_category}:{REASON_STALE_CATEGORY}")

    assessment = InformationLatencyAssessment(
        prediction_id=prediction.id,
        horizon_days=prediction.horizon_days,
        sla_multiplier=multiplier,
        category_latency_seconds=category_latency_seconds,
        sla_violations=sla_violations,
        suppress_eligibility=len(sla_violations) > 0,
        reasons=reasons,
        evaluated_at=evaluated_at,
        latency_rule_version=LATENCY_RULE_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_latency_history(session: Session, prediction_id: int) -> tuple[InformationLatencyAssessment, ...]:
    return tuple(
        session.scalars(
            select(InformationLatencyAssessment)
            .where(InformationLatencyAssessment.prediction_id == prediction_id)
            .order_by(InformationLatencyAssessment.id.asc())
        ).all()
    )


def _average_ingestion_latency_seconds(session: Session, *, data_type: str, window: EvaluationWindow) -> tuple[int, Decimal | None]:
    query = select(DataFetchAttempt.requested_at, DataFetchAttempt.source_timestamp).where(
        DataFetchAttempt.data_type == data_type,
        DataFetchAttempt.success.is_(True),
        DataFetchAttempt.source_timestamp.is_not(None),
    )
    if window.start is not None:
        query = query.where(DataFetchAttempt.requested_at >= window.start)
    if window.end is not None:
        query = query.where(DataFetchAttempt.requested_at <= window.end)

    rows = session.execute(query).all()
    latencies = [
        (requested_at.replace(tzinfo=None) - source_timestamp.replace(tzinfo=None)).total_seconds()
        for requested_at, source_timestamp in rows
    ]
    if not latencies:
        return 0, None
    return len(latencies), Decimal(sum(latencies)) / Decimal(len(latencies))


def measure_latency_degradation(
    session: Session,
    *,
    data_type: str,
    window: EvaluationWindow,
    baseline_window: EvaluationWindow,
    computed_at: datetime,
) -> LatencyDegradationReport:
    """Always computes and persists a fresh, independent report -- never
    mutates a prior measurement (AC: "historical freshness values are
    immutable")."""
    sample_count, average_latency_seconds = _average_ingestion_latency_seconds(session, data_type=data_type, window=window)
    baseline_sample_count, baseline_average_latency_seconds = _average_ingestion_latency_seconds(
        session, data_type=data_type, window=baseline_window
    )

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or baseline_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        degradation_ratio = None
    else:
        degradation_ratio = (
            (average_latency_seconds - baseline_average_latency_seconds) / baseline_average_latency_seconds
            if baseline_average_latency_seconds != 0
            else None
        )
        if degradation_ratio is None:
            verdict = VERDICT_INSUFFICIENT_SAMPLE
        elif degradation_ratio >= WEAKNESS_MARGIN:
            verdict = VERDICT_DEGRADED
        elif degradation_ratio <= -WEAKNESS_MARGIN:
            verdict = VERDICT_IMPROVED
        else:
            verdict = VERDICT_STABLE

    report = LatencyDegradationReport(
        data_type=data_type,
        window_label=window.label,
        sample_count=sample_count,
        average_latency_seconds=average_latency_seconds,
        baseline_sample_count=baseline_sample_count,
        baseline_average_latency_seconds=baseline_average_latency_seconds,
        degradation_ratio=degradation_ratio,
        verdict=verdict,
        computed_at=computed_at,
        report_rule_version=DEGRADATION_RULE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_degradation_report_history(session: Session, data_type: str) -> tuple[LatencyDegradationReport, ...]:
    return tuple(
        session.scalars(
            select(LatencyDegradationReport)
            .where(LatencyDegradationReport.data_type == data_type)
            .order_by(LatencyDegradationReport.id.asc())
        ).all()
    )

"""EPIC-M1.85: determine which evidence, features, market conditions
and model signals are *associated with* successful and failed positive
predictions -- never claiming causal impact when only predictive
association is established.

`capture_attribution_snapshot` composes rather than duplicates: the
feature/evidence values are read from M1.66's already-immutable
`RecommendationDecisionTrace` (never re-derived), and the outcome from
M1.5's `PredictionOutcome`. This module's only genuinely new
contribution is (1) bucketing two continuous features
(`sma20_distance`, `volume_ratio_20d`) into fixed, documented,
versioned bands, and (2) `compute_factor_association_report`, which
measures each factor value's *success-rate association*, deliberately
never named or reasoned about as causation anywhere in this module.

Every verdict name is deliberately association-flavored --
`CONSISTENTLY_ASSOCIATED_WITH_SUCCESS`/`_FAILURE`, never "causes,"
"drives," or "explains" -- matching the scope's own constraint.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .decision_trace import get_decision_trace
from .market_regime import classify_market_regime
from .models import (
    FactorAssociationReport,
    Prediction,
    PredictionAttributionSnapshot,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
)
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

ATTRIBUTION_RULE_VERSION = "ATB-001"
ASSOCIATION_REPORT_VERSION = "FAR-001"

BUCKET_WEAK = "WEAK"
BUCKET_MODERATE = "MODERATE"
BUCKET_STRONG = "STRONG"

VOLUME_BUCKET_LOW = "LOW"
VOLUME_BUCKET_NORMAL = "NORMAL"
VOLUME_BUCKET_HIGH = "HIGH"

# Fixed, documented, versioned bucket thresholds -- not learned or fitted.
SMA20_DISTANCE_THRESHOLDS = ((Decimal("0.06"), BUCKET_STRONG), (Decimal("0.03"), BUCKET_MODERATE))
SMA20_DISTANCE_FALLBACK = BUCKET_WEAK

VOLUME_RATIO_THRESHOLDS = ((Decimal("2.0"), VOLUME_BUCKET_HIGH), (Decimal("1.2"), VOLUME_BUCKET_NORMAL))
VOLUME_RATIO_FALLBACK = VOLUME_BUCKET_LOW

DIMENSION_HORIZON = "HORIZON_DAYS"
DIMENSION_REGIME = "REGIME"
DIMENSION_SMA20_DISTANCE = "SMA20_DISTANCE_BUCKET"
DIMENSION_VOLUME_RATIO = "VOLUME_RATIO_BUCKET"
DIMENSION_EVIDENCE_AVAILABLE = "EVIDENCE_AVAILABLE"

ASSOCIATION_SUCCESS = "CONSISTENTLY_ASSOCIATED_WITH_SUCCESS"
ASSOCIATION_FAILURE = "CONSISTENTLY_ASSOCIATED_WITH_FAILURE"
ASSOCIATION_NONE = "NO_CONSISTENT_ASSOCIATION"
ASSOCIATION_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

REPORT_VERDICT_MEASURED = "MEASURED"
REPORT_VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

_ALL_EVIDENCE_CATEGORIES = ("FUNDAMENTAL", "NEWS", "EVENT", "MARKET_SECTOR", "TECHNICAL_VOLUME")


class PredictionAttributionSnapshotImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "model_version",
    "horizon_days",
    "regime",
    "sma20_distance_bucket",
    "volume_ratio_bucket",
    "evidence_categories_available",
    "outcome",
    "snapshotted_at",
    "attribution_rule_version",
    "created_at",
)


@event.listens_for(PredictionAttributionSnapshot, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise PredictionAttributionSnapshotImmutableError(
            f"prediction attribution snapshot {target.id} field(s) {changed} cannot be modified after creation"
        )


def _bucket(value: Decimal | None, thresholds: tuple, fallback: str) -> str | None:
    if value is None:
        return None
    for threshold, bucket in thresholds:
        if value >= threshold:
            return bucket
    return fallback


def get_attribution_snapshot(session: Session, prediction_id: int) -> PredictionAttributionSnapshot | None:
    return session.scalar(
        select(PredictionAttributionSnapshot).where(PredictionAttributionSnapshot.prediction_id == prediction_id)
    )


def capture_attribution_snapshot(
    session: Session, prediction: Prediction, *, snapshotted_at: datetime
) -> PredictionAttributionSnapshot | None:
    """Idempotent per `prediction_id`: an already-captured snapshot is
    returned unchanged (AC: "historical attribution is immutable").
    Returns `None` -- never fabricates a snapshot -- when this
    prediction has neither an evaluated outcome nor a captured M1.66
    decision trace yet (scope: "every *eligible* prediction," not every
    prediction regardless of state)."""
    existing = get_attribution_snapshot(session, prediction.id)
    if existing is not None:
        return existing

    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id))
    if outcome is None or outcome.outcome not in ("SUCCESS", "FAILURE"):
        return None

    generation = session.scalar(select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction.id))
    trace = get_decision_trace(session, generation.id) if generation is not None else None
    if trace is None:
        return None

    snapshot = PredictionAttributionSnapshot(
        prediction_id=prediction.id,
        model_version=prediction.model_version,
        horizon_days=prediction.horizon_days,
        regime=_regime_for_generation(session, generation),
        sma20_distance_bucket=_bucket(trace.sma20_distance, SMA20_DISTANCE_THRESHOLDS, SMA20_DISTANCE_FALLBACK),
        volume_ratio_bucket=_bucket(trace.volume_ratio_20d, VOLUME_RATIO_THRESHOLDS, VOLUME_RATIO_FALLBACK),
        evidence_categories_available=[
            item["category"] for item in trace.evidence_categories_snapshot if item.get("status") == "AVAILABLE"
        ],
        outcome=outcome.outcome,
        snapshotted_at=snapshotted_at,
        attribution_rule_version=ATTRIBUTION_RULE_VERSION,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _regime_for_generation(session: Session, generation: RecommendationGeneration) -> str | None:
    scan_candidate = session.get(ScanCandidate, generation.scan_candidate_id)
    if scan_candidate is None:
        return None
    return classify_market_regime(session, scan_candidate.scan_id).regime


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _factor_values(snapshot: PredictionAttributionSnapshot) -> list[tuple[str, str]]:
    values = [
        (DIMENSION_HORIZON, str(snapshot.horizon_days)),
        (DIMENSION_SMA20_DISTANCE, snapshot.sma20_distance_bucket),
        (DIMENSION_VOLUME_RATIO, snapshot.volume_ratio_bucket),
    ]
    if snapshot.regime is not None:
        values.append((DIMENSION_REGIME, snapshot.regime))
    for category in _ALL_EVIDENCE_CATEGORIES:
        available = category in snapshot.evidence_categories_available
        values.append((DIMENSION_EVIDENCE_AVAILABLE, f"{category}={'YES' if available else 'NO'}"))
    return [(dimension, value) for dimension, value in values if value is not None]


def compute_factor_association_report(
    session: Session, *, scope_label: str, computed_at: datetime
) -> FactorAssociationReport:
    """Deterministic, reproducible aggregate over already-immutable
    attribution snapshots (AC: "attribution is reproducible from
    historical inputs"). Below `MIN_SAMPLE_SIZE_FOR_COMPARISON`, the
    whole report -- and every individual factor value -- is explicitly
    `INSUFFICIENT_SAMPLE`, never an unsafe conclusion from a sparse
    dataset."""
    snapshots = session.scalars(select(PredictionAttributionSnapshot)).all()
    sample_count = len(snapshots)

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        report = FactorAssociationReport(
            scope_label=scope_label, sample_count=sample_count, baseline_success_rate=None,
            factor_associations=[], verdict=REPORT_VERDICT_INSUFFICIENT_SAMPLE, computed_at=computed_at,
            report_rule_version=ASSOCIATION_REPORT_VERSION,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    baseline_success_rate = _rate(sum(1 for s in snapshots if s.outcome == "SUCCESS"), sample_count)

    grouped: dict[tuple[str, str], list[str]] = {}
    for snapshot in snapshots:
        for dimension, value in _factor_values(snapshot):
            grouped.setdefault((dimension, value), []).append(snapshot.outcome)

    associations = []
    for (dimension, value) in sorted(grouped):
        outcomes = grouped[(dimension, value)]
        group_sample_count = len(outcomes)
        if group_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
            associations.append({
                "dimension": dimension, "value": value, "sample_count": group_sample_count,
                "success_rate": None, "association": ASSOCIATION_INSUFFICIENT_SAMPLE,
            })
            continue
        success_rate = _rate(sum(1 for o in outcomes if o == "SUCCESS"), group_sample_count)
        delta = success_rate - baseline_success_rate
        if delta >= WEAKNESS_MARGIN:
            association = ASSOCIATION_SUCCESS
        elif delta <= -WEAKNESS_MARGIN:
            association = ASSOCIATION_FAILURE
        else:
            association = ASSOCIATION_NONE
        associations.append({
            "dimension": dimension, "value": value, "sample_count": group_sample_count,
            "success_rate": str(success_rate), "association": association,
        })

    report = FactorAssociationReport(
        scope_label=scope_label,
        sample_count=sample_count,
        baseline_success_rate=baseline_success_rate,
        factor_associations=associations,
        verdict=REPORT_VERDICT_MEASURED,
        computed_at=computed_at,
        report_rule_version=ASSOCIATION_REPORT_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_association_report_history(session: Session) -> tuple[FactorAssociationReport, ...]:
    return tuple(session.scalars(select(FactorAssociationReport).order_by(FactorAssociationReport.id.asc())).all())

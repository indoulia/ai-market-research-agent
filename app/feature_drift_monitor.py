"""EPIC-M1.101: detect changes in input data and feature distributions
that can make a previously reliable model less trustworthy even before
outcome-based regression (M1.67) becomes visible.

Monitors exactly the real, already-captured numeric feature columns
`app.scan`'s real pipeline produces on `ScanCandidate` -- `SMA20_DISTANCE`,
`VOLUME_RATIO_20D`, `ATR_PERCENT` (technical/engineered) and
`PREDICTED_PROBABILITY`/`CONFIDENCE` (model-output features) -- a fixed,
documented vocabulary, not an open-ended one, so no drift check can ever
silently reference a feature this platform doesn't really compute.
"Feature importance drift" (scope) is a genuine, honest gap: this
platform has no model-interpretability/feature-importance store yet
(no EPIC has built one) -- rather than fabricate a plausible-looking
number, this module omits it entirely and documents the gap here,
matching the same honesty this platform's provider/benchmark EPICs
already established (M1.90's zero-real `AIDiscoveryProvider`, M1.93's
`estimated_cost_usd = None`).

"Detect missingness, freshness and coverage drift" (scope) reuses
`ScanCandidate.data_quality_passed` -- the real, already-computed
per-candidate data-quality verdict `app.scan` produces -- as the
coverage signal, rather than inventing a second missingness metric on
top of it.

Every registered `FeatureReferenceDistribution` is immutable once set
(AC: "historical reference distributions remain immutable") -- there is
no update path, only registration (idempotent, rejecting redefinition)
and read-only comparison. `trust_reduction_recommended` is a signal
only (AC: "drift can affect Trust Score through explicit policy") --
this module has no write path to `PredictionTrustScore` or
`TrustControlDecision`; wiring it into M1.84's already-merged
consolidation is left to a future revision, the same posture M1.80's
and M1.83's own `trust_reduction_recommended` fields already established
before `trust_control.py` composed them.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    CoverageDriftAssessment,
    DailyCandidateScan,
    FeatureDriftAssessment,
    FeatureReferenceDistribution,
    ScanCandidate,
)
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

FEATURE_DRIFT_VERSION = "FDM-001"

FEATURE_SMA20_DISTANCE = "SMA20_DISTANCE"
FEATURE_VOLUME_RATIO_20D = "VOLUME_RATIO_20D"
FEATURE_ATR_PERCENT = "ATR_PERCENT"
FEATURE_PREDICTED_PROBABILITY = "PREDICTED_PROBABILITY"
FEATURE_CONFIDENCE = "CONFIDENCE"

_FEATURE_COLUMNS = {
    FEATURE_SMA20_DISTANCE: ScanCandidate.sma20_distance,
    FEATURE_VOLUME_RATIO_20D: ScanCandidate.volume_ratio_20d,
    FEATURE_ATR_PERCENT: ScanCandidate.atr_percent,
    FEATURE_PREDICTED_PROBABILITY: ScanCandidate.predicted_probability,
    FEATURE_CONFIDENCE: ScanCandidate.confidence,
}

# Public vocabulary of every feature this module monitors, for callers
# (e.g. M1.102) that need to iterate all of them without reaching into
# this module's internal column mapping.
MONITORED_FEATURES = tuple(_FEATURE_COLUMNS)

VERDICT_NO_DRIFT = "NO_DRIFT"
VERDICT_DRIFT_DETECTED = "DRIFT_DETECTED"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

# Fixed, documented, versioned policy constant: a live mean more than this
# many reference standard deviations away from the reference mean is
# material drift -- not learned or fitted.
DRIFT_THRESHOLD_STD = Decimal("2")


class UnknownFeatureError(ValueError):
    pass


class InsufficientReferenceSampleError(RuntimeError):
    """A reference distribution may never be registered from a sparse sample."""


class UnknownReferenceDistributionError(RuntimeError):
    pass


def _feature_values(session: Session, feature_name: str, model_version: str, window: EvaluationWindow) -> list[Decimal]:
    if feature_name not in _FEATURE_COLUMNS:
        raise UnknownFeatureError(f"'{feature_name}' is not a monitored feature")
    column = _FEATURE_COLUMNS[feature_name]
    query = (
        select(column)
        .select_from(ScanCandidate)
        .join(DailyCandidateScan, DailyCandidateScan.id == ScanCandidate.scan_id)
        .where(ScanCandidate.model_version == model_version, column.isnot(None))
    )
    if window.start is not None:
        query = query.where(DailyCandidateScan.scan_date >= window.start.date())
    if window.end is not None:
        query = query.where(DailyCandidateScan.scan_date <= window.end.date())
    return [v for v in session.scalars(query).all() if v is not None]


def get_reference_distribution(
    session: Session, *, model_version: str, feature_name: str
) -> FeatureReferenceDistribution | None:
    return session.scalar(
        select(FeatureReferenceDistribution).where(
            FeatureReferenceDistribution.model_version == model_version,
            FeatureReferenceDistribution.feature_name == feature_name,
        )
    )


def register_reference_distribution(
    session: Session, *, model_version: str, feature_name: str, window: EvaluationWindow, registered_at: datetime
) -> FeatureReferenceDistribution:
    """Idempotent by `(model_version, feature_name)`: a reference already
    registered for this model/feature is returned unchanged, even if a
    different `window`/statistics would be computed today -- registration
    happens at most once per model version (AC: "historical reference
    distributions remain immutable"). Raises `InsufficientReferenceSampleError`
    rather than freezing a reference from too sparse a sample."""
    existing = get_reference_distribution(session, model_version=model_version, feature_name=feature_name)
    if existing is not None:
        return existing

    values = _feature_values(session, feature_name, model_version, window)
    if len(values) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        raise InsufficientReferenceSampleError(
            f"only {len(values)} samples available for '{feature_name}'; need at least {MIN_SAMPLE_SIZE_FOR_COMPARISON}"
        )

    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else Decimal("0")

    reference = FeatureReferenceDistribution(
        model_version=model_version, feature_name=feature_name, window_label=window.label,
        sample_count=len(values), mean=mean, stdev=stdev, registered_at=registered_at,
        reference_version=FEATURE_DRIFT_VERSION,
    )
    session.add(reference)
    session.commit()
    session.refresh(reference)
    return reference


def detect_feature_drift(
    session: Session, *, model_version: str, feature_name: str, monitoring_window: EvaluationWindow, evaluated_at: datetime
) -> FeatureDriftAssessment:
    """Idempotent by `(model_version, feature_name, evaluated_at)`. Raises
    `UnknownReferenceDistributionError` if no reference has been
    registered yet -- this module never invents a baseline to compare
    against (AC: "compare live distributions with validated
    training/reference distributions")."""
    existing = session.scalar(
        select(FeatureDriftAssessment).where(
            FeatureDriftAssessment.model_version == model_version,
            FeatureDriftAssessment.feature_name == feature_name,
            FeatureDriftAssessment.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    reference = get_reference_distribution(session, model_version=model_version, feature_name=feature_name)
    if reference is None:
        raise UnknownReferenceDistributionError(f"no reference distribution registered for '{feature_name}' on model '{model_version}'")

    live_values = _feature_values(session, feature_name, model_version, monitoring_window)
    monitoring_sample_count = len(live_values)

    monitoring_mean: Decimal | None = None
    drift_magnitude: Decimal | None = None
    if monitoring_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or reference.sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        verdict = VERDICT_INSUFFICIENT_SAMPLE
    else:
        monitoring_mean = statistics.mean(live_values)
        if reference.stdev == 0:
            # A zero-variance reference cannot be standardized against --
            # honestly abstain rather than divide by zero or fabricate a verdict.
            verdict = VERDICT_INSUFFICIENT_SAMPLE
        else:
            drift_magnitude = abs(monitoring_mean - reference.mean) / reference.stdev
            verdict = VERDICT_DRIFT_DETECTED if drift_magnitude >= DRIFT_THRESHOLD_STD else VERDICT_NO_DRIFT

    assessment = FeatureDriftAssessment(
        model_version=model_version, feature_name=feature_name, monitoring_window_label=monitoring_window.label,
        monitoring_sample_count=monitoring_sample_count, monitoring_mean=monitoring_mean,
        drift_magnitude=drift_magnitude, verdict=verdict,
        trust_reduction_recommended=(verdict == VERDICT_DRIFT_DETECTED),
        evaluated_at=evaluated_at, drift_rule_version=FEATURE_DRIFT_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_feature_drift_history(session: Session, *, model_version: str, feature_name: str) -> tuple[FeatureDriftAssessment, ...]:
    return tuple(
        session.scalars(
            select(FeatureDriftAssessment)
            .where(FeatureDriftAssessment.model_version == model_version, FeatureDriftAssessment.feature_name == feature_name)
            .order_by(FeatureDriftAssessment.id.asc())
        ).all()
    )


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _coverage_stats(session: Session, model_version: str, window: EvaluationWindow) -> tuple[int, int]:
    query = (
        select(ScanCandidate.data_quality_passed)
        .select_from(ScanCandidate)
        .join(DailyCandidateScan, DailyCandidateScan.id == ScanCandidate.scan_id)
        .where(ScanCandidate.model_version == model_version, ScanCandidate.data_quality_passed.isnot(None))
    )
    if window.start is not None:
        query = query.where(DailyCandidateScan.scan_date >= window.start.date())
    if window.end is not None:
        query = query.where(DailyCandidateScan.scan_date <= window.end.date())
    values = list(session.scalars(query).all())
    return len(values), sum(1 for v in values if v)


def detect_coverage_drift(
    session: Session,
    *,
    model_version: str,
    reference_window: EvaluationWindow,
    monitoring_window: EvaluationWindow,
    evaluated_at: datetime,
) -> CoverageDriftAssessment:
    """Idempotent by `(model_version, evaluated_at)`. Only a *drop* in
    data-quality-passed coverage counts as drift -- an improvement is
    never flagged (scope: "surfaced before it silently contaminates
    learning" is about degradation, not any change)."""
    existing = session.scalar(
        select(CoverageDriftAssessment).where(
            CoverageDriftAssessment.model_version == model_version, CoverageDriftAssessment.evaluated_at == evaluated_at
        )
    )
    if existing is not None:
        return existing

    reference_count, reference_passed = _coverage_stats(session, model_version, reference_window)
    monitoring_count, monitoring_passed = _coverage_stats(session, model_version, monitoring_window)
    reference_rate = _rate(reference_passed, reference_count)
    monitoring_rate = _rate(monitoring_passed, monitoring_count)

    if (
        reference_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or monitoring_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or reference_rate is None
        or monitoring_rate is None
    ):
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        coverage_rate_delta = None
    else:
        coverage_rate_delta = monitoring_rate - reference_rate
        verdict = VERDICT_DRIFT_DETECTED if coverage_rate_delta <= -WEAKNESS_MARGIN else VERDICT_NO_DRIFT

    assessment = CoverageDriftAssessment(
        model_version=model_version, reference_window_label=reference_window.label,
        monitoring_window_label=monitoring_window.label, reference_sample_count=reference_count,
        monitoring_sample_count=monitoring_count, reference_coverage_rate=reference_rate,
        monitoring_coverage_rate=monitoring_rate, coverage_rate_delta=coverage_rate_delta, verdict=verdict,
        trust_reduction_recommended=(verdict == VERDICT_DRIFT_DETECTED), evaluated_at=evaluated_at,
        drift_rule_version=FEATURE_DRIFT_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_coverage_drift_history(session: Session, model_version: str) -> tuple[CoverageDriftAssessment, ...]:
    return tuple(
        session.scalars(
            select(CoverageDriftAssessment)
            .where(CoverageDriftAssessment.model_version == model_version)
            .order_by(CoverageDriftAssessment.id.asc())
        ).all()
    )

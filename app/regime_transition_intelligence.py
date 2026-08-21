"""EPIC-M1.102: detect unstable market-regime transitions and separate
inherent market uncertainty from insufficient model/data knowledge, so
Trust Score and positive-only gating can respond appropriately.

Never reclassifies a regime itself -- `detect_regime_transition` only
reads M1.26's already-computed `MarketRegime` for the current scan and
its immediately preceding scan (same `universe_version`, ordered by
`scan_date`); it has no write path to `MarketRegime` at all.

"Distinguish market uncertainty from data/model uncertainty where
feasible" (scope) is realized honestly by composing two already-real,
independent signals rather than inventing a third: MARKET uncertainty is
this module's own boundary-proximity measure over M1.26's
`breadth_positive_ratio` (how close the breadth ratio sits to either
trend threshold -- a classification that could flip with a small change
in market breadth is inherently uncertain, regardless of any model);
MODEL uncertainty is M1.101's already-computed `trust_reduction_
recommended` feature/coverage drift signals for the same model version
around the same time (a model whose own recent input data looks
different from its reference distribution is uncertain for reasons that
have nothing to do with the market's breadth). Never claims to separate
them when only one or neither is present -- `uncertainty_source` is
`NONE`/`MARKET`/`MODEL`/`MARKET_AND_MODEL`, an honest enumeration, not a
forced binary split.

Per this EPIC's own Execution Rule (also mirrored in the AC): this
module never produces a negative/cautious user-facing state -- it has no
write path to `Prediction`, `PositiveRecommendationGateDecision`, or any
recommendation-facing table. `trust_reduction_recommended` is a
propose-only signal a future revision of M1.84's `trust_control` may
compose, the same posture M1.80/M1.83/M1.101's own flags already
established before being composed.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .feature_drift_monitor import MONITORED_FEATURES, get_coverage_drift_history, get_feature_drift_history
from .market_regime import BEARISH_BREADTH_THRESHOLD, BULLISH_BREADTH_THRESHOLD, classify_market_regime
from .models import (
    DailyCandidateScan,
    MarketRegime,
    Prediction,
    PredictionOutcome,
    PredictionRegimeUncertaintySnapshot,
    RecommendationGeneration,
    RegimeTransitionAssessment,
    ScanCandidate,
    TransitionPeriodPerformanceReport,
)
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

REGIME_TRANSITION_VERSION = "RTI-001"

VERDICT_STABLE = "STABLE"
VERDICT_NEAR_BOUNDARY = "NEAR_BOUNDARY"

SOURCE_NONE = "NONE"
SOURCE_MARKET = "MARKET"
SOURCE_MODEL = "MODEL"
SOURCE_MARKET_AND_MODEL = "MARKET_AND_MODEL"

REPORT_VERDICT_MEASURED = "MEASURED"
REPORT_VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

# Fixed, documented, versioned policy constant: a breadth ratio within this
# margin of either trend threshold is close enough to flip on a small change
# in market breadth -- not learned or fitted.
UNSTABLE_BOUNDARY_MARGIN = Decimal("0.05")


class MissingCurrentRegimeError(RuntimeError):
    pass


def _distance_to_boundary(breadth_positive_ratio: Decimal) -> Decimal:
    return min(abs(breadth_positive_ratio - BULLISH_BREADTH_THRESHOLD), abs(breadth_positive_ratio - BEARISH_BREADTH_THRESHOLD))


def _previous_scan_regime(session: Session, scan: DailyCandidateScan) -> tuple[int | None, str | None]:
    previous_scan = session.scalar(
        select(DailyCandidateScan)
        .where(DailyCandidateScan.universe_version == scan.universe_version, DailyCandidateScan.scan_date < scan.scan_date)
        .order_by(DailyCandidateScan.scan_date.desc())
    )
    if previous_scan is None:
        return None, None
    previous_regime = session.scalar(select(MarketRegime).where(MarketRegime.scan_id == previous_scan.id))
    if previous_regime is None:
        return previous_scan.id, None
    return previous_scan.id, previous_regime.regime


def _model_uncertainty_active(session: Session, model_version: str | None) -> bool:
    if model_version is None:
        return False
    for feature_name in MONITORED_FEATURES:
        history = get_feature_drift_history(session, model_version=model_version, feature_name=feature_name)
        if history and history[-1].trust_reduction_recommended:
            return True
    coverage_history = get_coverage_drift_history(session, model_version)
    return bool(coverage_history and coverage_history[-1].trust_reduction_recommended)


def detect_regime_transition(
    session: Session, scan_id: int, *, detected_at: datetime, model_version: str | None = None
) -> RegimeTransitionAssessment:
    """Idempotent by `scan_id`. Raises `MissingCurrentRegimeError` if
    M1.26 has not classified this scan yet -- this module never
    classifies a regime itself."""
    existing = session.scalar(select(RegimeTransitionAssessment).where(RegimeTransitionAssessment.scan_id == scan_id))
    if existing is not None:
        return existing

    current_regime = session.scalar(select(MarketRegime).where(MarketRegime.scan_id == scan_id))
    if current_regime is None:
        raise MissingCurrentRegimeError(f"scan {scan_id} has no MarketRegime classification yet")

    scan = session.get(DailyCandidateScan, scan_id)
    previous_scan_id, previous_regime_label = _previous_scan_regime(session, scan)
    transition_detected = previous_regime_label is not None and previous_regime_label != current_regime.regime

    distance_to_boundary = _distance_to_boundary(current_regime.breadth_positive_ratio)
    boundary_instability_verdict = VERDICT_NEAR_BOUNDARY if distance_to_boundary <= UNSTABLE_BOUNDARY_MARGIN else VERDICT_STABLE

    market_uncertain = transition_detected and boundary_instability_verdict == VERDICT_NEAR_BOUNDARY
    model_uncertain = _model_uncertainty_active(session, model_version)
    if market_uncertain and model_uncertain:
        uncertainty_source = SOURCE_MARKET_AND_MODEL
    elif market_uncertain:
        uncertainty_source = SOURCE_MARKET
    elif model_uncertain:
        uncertainty_source = SOURCE_MODEL
    else:
        uncertainty_source = SOURCE_NONE

    assessment = RegimeTransitionAssessment(
        scan_id=scan_id, previous_scan_id=previous_scan_id, current_regime=current_regime.regime,
        previous_regime=previous_regime_label, transition_detected=transition_detected,
        distance_to_boundary=distance_to_boundary, boundary_instability_verdict=boundary_instability_verdict,
        uncertainty_source=uncertainty_source, trust_reduction_recommended=market_uncertain,
        detected_at=detected_at, assessment_rule_version=REGIME_TRANSITION_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_transition_assessment(session: Session, scan_id: int) -> RegimeTransitionAssessment | None:
    return session.scalar(select(RegimeTransitionAssessment).where(RegimeTransitionAssessment.scan_id == scan_id))


def _scan_id_for_prediction(session: Session, prediction_id: int) -> int | None:
    return session.scalar(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction_id)
    )


def snapshot_prediction_regime_uncertainty(
    session: Session, prediction: Prediction, *, snapshotted_at: datetime
) -> PredictionRegimeUncertaintySnapshot | None:
    """Idempotent per `prediction_id`. Returns `None` -- never fabricates
    a snapshot -- if this prediction's scan has no transition assessment
    yet (AC: "preserve regime and uncertainty snapshots with
    predictions")."""
    existing = session.scalar(
        select(PredictionRegimeUncertaintySnapshot).where(PredictionRegimeUncertaintySnapshot.prediction_id == prediction.id)
    )
    if existing is not None:
        return existing

    scan_id = _scan_id_for_prediction(session, prediction.id)
    if scan_id is None:
        return None
    assessment = get_transition_assessment(session, scan_id)
    if assessment is None:
        return None

    snapshot = PredictionRegimeUncertaintySnapshot(
        prediction_id=prediction.id, regime_transition_assessment_id=assessment.id, snapshotted_at=snapshotted_at,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_regime_uncertainty_snapshot(session: Session, prediction_id: int) -> PredictionRegimeUncertaintySnapshot | None:
    return session.scalar(
        select(PredictionRegimeUncertaintySnapshot).where(PredictionRegimeUncertaintySnapshot.prediction_id == prediction_id)
    )


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _outcomes_by_transition_flag(session: Session, window: EvaluationWindow, transition_flag: bool) -> list[str]:
    query = (
        select(PredictionOutcome.outcome)
        .select_from(PredictionOutcome)
        .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
        .join(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .join(RegimeTransitionAssessment, RegimeTransitionAssessment.scan_id == ScanCandidate.scan_id)
        .where(
            RegimeTransitionAssessment.transition_detected.is_(transition_flag),
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
    )
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.scalars(query).all())


def evaluate_transition_period_performance(
    session: Session, *, window: EvaluationWindow, computed_at: datetime
) -> TransitionPeriodPerformanceReport:
    """Always computes and persists a fresh, independent report row (the
    same "report," not "per-entity decision," posture already used by
    M1.85's `FactorAssociationReport` and M1.99's `RankingEffectivenessReport`)."""
    transition_outcomes = _outcomes_by_transition_flag(session, window, True)
    stable_outcomes = _outcomes_by_transition_flag(session, window, False)

    transition_sample_count = len(transition_outcomes)
    stable_sample_count = len(stable_outcomes)
    transition_success_count = sum(1 for o in transition_outcomes if o == "SUCCESS")
    stable_success_count = sum(1 for o in stable_outcomes if o == "SUCCESS")
    transition_success_rate = _rate(transition_success_count, transition_sample_count)
    stable_success_rate = _rate(stable_success_count, stable_sample_count)

    if transition_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or stable_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        verdict = REPORT_VERDICT_INSUFFICIENT_SAMPLE
        success_rate_delta = None
    else:
        success_rate_delta = transition_success_rate - stable_success_rate
        verdict = REPORT_VERDICT_MEASURED

    report = TransitionPeriodPerformanceReport(
        window_label=window.label, transition_sample_count=transition_sample_count,
        transition_success_count=transition_success_count, transition_success_rate=transition_success_rate,
        stable_sample_count=stable_sample_count, stable_success_count=stable_success_count,
        stable_success_rate=stable_success_rate, success_rate_delta=success_rate_delta, verdict=verdict,
        computed_at=computed_at, report_rule_version=REGIME_TRANSITION_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_transition_performance_history(session: Session) -> tuple[TransitionPeriodPerformanceReport, ...]:
    return tuple(
        session.scalars(select(TransitionPeriodPerformanceReport).order_by(TransitionPeriodPerformanceReport.id.asc())).all()
    )

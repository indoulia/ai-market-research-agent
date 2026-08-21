"""EPIC-M1.89: make the evolution of prediction quality, trust and
learning visible over time, and let a reader drill down from an
aggregate trust picture to one prediction's full evidence trail.

Purely a read-only composition over already-immutable evidence this
platform's own EPICs already computed and persisted -- like M1.16's
`compute_trust_report` before it, this module introduces no new
measurement, no new table, and no persistence of its own; it only
assembles existing history accessors into one coherent snapshot per
`model_version` (`build_trust_dashboard`) or one prediction
(`get_prediction_trust_drilldown`).

"Show suppressed-candidate statistics without presenting negative
recommendations as user recommendations" (scope) is honored structurally:
`suppression_reason_counts` reports only the fixed M1.81 vocabulary of
*why* a candidate was suppressed, never the candidate's own name/symbol
paired with a "recommendation," and this module has no write path to
any recommendation-facing table at all.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .horizon_regime_trust import SEGMENT_COMBINED, get_trust_history
from .model_promotion import get_promotion_history
from .model_regression_detection import get_regression_history
from .models import (
    HorizonRegimeTrust,
    HorizonUsefulnessReport,
    LearningHypothesis,
    ModelPromotion,
    ModelRegressionCheck,
    Prediction,
    PredictionAttributionSnapshot,
    PredictionCalibrationDrift,
    PredictionOutcome,
    PredictionQualityBenchmarkReport,
    PredictionStabilityAssessment,
    PredictionTrustScore,
    PredictionUsefulnessAssessment,
    PositiveRecommendationGateDecision,
    EvidenceQualityDecision,
    TrustControlDecision,
)
from .positive_recommendation_gate import VERDICT_GATE_PASS, VERDICT_GATE_SUPPRESSED, get_gate_decision_history
from .prediction_attribution import get_attribution_snapshot
from .prediction_calibration_drift import get_drift_history
from .prediction_quality_benchmark import get_benchmark_report_history
from .prediction_stability import get_stability_history
from .prediction_trust_score import get_trust_score_history
from .prediction_usefulness import get_usefulness_assessment, get_usefulness_report_history
from .evidence_quality_gate import get_quality_decision_history
from .self_correction_loop import get_hypothesis_history
from .trust_control import get_control_decision_history

DASHBOARD_VERSION = "TDB-001"

DEFAULT_HORIZONS = (1, 3, 5, 7)


@dataclass(frozen=True)
class TrustDashboardSnapshot:
    dashboard_version: str
    model_version: str
    trust_score_trend: tuple[PredictionTrustScore, ...]
    benchmark_history: tuple[PredictionQualityBenchmarkReport, ...]
    calibration_drift_history: tuple[PredictionCalibrationDrift, ...]
    usefulness_by_horizon: dict[int, tuple[HorizonUsefulnessReport, ...]]
    regime_trust: tuple[HorizonRegimeTrust, ...]
    promotion_history: tuple[ModelPromotion, ...]
    regression_history: tuple[ModelRegressionCheck, ...]
    learning_hypothesis_history: tuple[LearningHypothesis, ...]
    positive_recommendation_count: int
    successful_recommendation_count: int
    suppressed_candidate_count: int
    suppression_reason_counts: dict[str, int]
    evidence_quality_state_counts: dict[str, int]


@dataclass(frozen=True)
class PredictionTrustDrilldown:
    prediction: Prediction
    outcome: PredictionOutcome | None
    trust_score_history: tuple[PredictionTrustScore, ...]
    gate_decision_history: tuple[PositiveRecommendationGateDecision, ...]
    trust_control_history: tuple[TrustControlDecision, ...]
    evidence_quality_history: tuple[EvidenceQualityDecision, ...]
    stability_history: tuple[PredictionStabilityAssessment, ...]
    attribution_snapshot: PredictionAttributionSnapshot | None
    usefulness_assessment: PredictionUsefulnessAssessment | None


def _prediction_ids_for_model_version(session: Session, model_version: str) -> list[int]:
    return list(session.scalars(select(Prediction.id).where(Prediction.model_version == model_version)).all())


def _trust_score_trend(session: Session, prediction_ids: list[int]) -> tuple[PredictionTrustScore, ...]:
    if not prediction_ids:
        return ()
    return tuple(
        session.scalars(
            select(PredictionTrustScore)
            .where(PredictionTrustScore.prediction_id.in_(prediction_ids))
            .order_by(PredictionTrustScore.computed_at.asc(), PredictionTrustScore.id.asc())
        ).all()
    )


def _latest_gate_decision_by_prediction(
    session: Session, prediction_ids: list[int]
) -> dict[int, PositiveRecommendationGateDecision]:
    latest: dict[int, PositiveRecommendationGateDecision] = {}
    if not prediction_ids:
        return latest
    decisions = session.scalars(
        select(PositiveRecommendationGateDecision)
        .where(PositiveRecommendationGateDecision.prediction_id.in_(prediction_ids))
        .order_by(PositiveRecommendationGateDecision.id.asc())
    ).all()
    for decision in decisions:
        latest[decision.prediction_id] = decision
    return latest


def _latest_evidence_quality_by_prediction(
    session: Session, prediction_ids: list[int]
) -> dict[int, EvidenceQualityDecision]:
    latest: dict[int, EvidenceQualityDecision] = {}
    if not prediction_ids:
        return latest
    decisions = session.scalars(
        select(EvidenceQualityDecision)
        .where(EvidenceQualityDecision.prediction_id.in_(prediction_ids))
        .order_by(EvidenceQualityDecision.id.asc())
    ).all()
    for decision in decisions:
        latest[decision.prediction_id] = decision
    return latest


def build_trust_dashboard(
    session: Session, *, model_version: str, horizons: tuple[int, ...] = DEFAULT_HORIZONS
) -> TrustDashboardSnapshot:
    """Assembles one coherent snapshot from already-computed, already-
    immutable evidence for `model_version` -- never recomputes any of the
    underlying signals, and persists nothing of its own."""
    prediction_ids = _prediction_ids_for_model_version(session, model_version)

    successful_recommendation_count = 0
    if prediction_ids:
        successful_recommendation_count = len(list(session.scalars(
            select(PredictionOutcome.id).where(
                PredictionOutcome.prediction_id.in_(prediction_ids), PredictionOutcome.outcome == "SUCCESS"
            )
        ).all()))

    latest_gate_decisions = _latest_gate_decision_by_prediction(session, prediction_ids)
    positive_recommendation_count = sum(
        1 for decision in latest_gate_decisions.values() if decision.verdict == VERDICT_GATE_PASS
    )
    suppressed_decisions = [d for d in latest_gate_decisions.values() if d.verdict == VERDICT_GATE_SUPPRESSED]
    suppression_reason_counts: dict[str, int] = {}
    for decision in suppressed_decisions:
        for reason in decision.suppression_reasons:
            suppression_reason_counts[reason] = suppression_reason_counts.get(reason, 0) + 1

    latest_evidence_quality = _latest_evidence_quality_by_prediction(session, prediction_ids)
    evidence_quality_state_counts: dict[str, int] = {}
    for decision in latest_evidence_quality.values():
        evidence_quality_state_counts[decision.state] = evidence_quality_state_counts.get(decision.state, 0) + 1

    usefulness_by_horizon = {
        horizon: get_usefulness_report_history(session, model_version=model_version, horizon_days=horizon)
        for horizon in horizons
    }

    return TrustDashboardSnapshot(
        dashboard_version=DASHBOARD_VERSION,
        model_version=model_version,
        trust_score_trend=_trust_score_trend(session, prediction_ids),
        benchmark_history=get_benchmark_report_history(session, model_version),
        calibration_drift_history=get_drift_history(session, model_version),
        usefulness_by_horizon=usefulness_by_horizon,
        regime_trust=get_trust_history(session, model_version=model_version, segment_type=SEGMENT_COMBINED),
        promotion_history=get_promotion_history(session, candidate_model_version=model_version),
        regression_history=get_regression_history(session, model_version),
        learning_hypothesis_history=get_hypothesis_history(session, model_version=model_version),
        positive_recommendation_count=positive_recommendation_count,
        successful_recommendation_count=successful_recommendation_count,
        suppressed_candidate_count=len(suppressed_decisions),
        suppression_reason_counts=suppression_reason_counts,
        evidence_quality_state_counts=evidence_quality_state_counts,
    )


def get_prediction_trust_drilldown(session: Session, prediction_id: int) -> PredictionTrustDrilldown:
    """Drills down from the aggregate dashboard to one prediction's full,
    already-immutable evidence trail (AC: "provide drill-down from
    aggregate trust to individual prediction history")."""
    prediction = session.get(Prediction, prediction_id)
    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction_id))
    return PredictionTrustDrilldown(
        prediction=prediction,
        outcome=outcome,
        trust_score_history=get_trust_score_history(session, prediction_id),
        gate_decision_history=get_gate_decision_history(session, prediction_id),
        trust_control_history=get_control_decision_history(session, prediction_id),
        evidence_quality_history=get_quality_decision_history(session, prediction_id),
        stability_history=get_stability_history(session, prediction_id),
        attribution_snapshot=get_attribution_snapshot(session, prediction_id),
        usefulness_assessment=get_usefulness_assessment(session, prediction_id),
    )

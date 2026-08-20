"""EPIC-M1.53: convert repeated, attributable user feedback (M1.52) into
measurable candidate learning signals, validated against objective outcomes
(M1.38) -- never altering production scoring by itself.

Read-only and deterministic; this module has no write path to `Prediction`,
`ScanCandidate`, or any scoring table at all, so "no production score
changes occur from feedback alone" (AC) holds structurally, not just by
convention -- there is no code path here that could make it happen. Every
signal produced is explicitly a *candidate* (scope: "produce candidate
learning signals; do not directly alter production scoring"), mirroring
M1.29/M1.30/M1.40's own "propose, never apply" posture for evidence derived
from historical data.

Reuses M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON`/`WEAKNESS_MARGIN` and
M1.28's `VERDICT_OK`/`VERDICT_WEAK`/`VERDICT_INSUFFICIENT_SAMPLE` vocabulary
(the same "is this segment's evidence reliable, and is it weak" question,
applied to a feedback category/reason instead of a discovery source) and
M1.22's `SCORE_BAND_COUNT`/`SCORE_BAND_WIDTH` for score-band segmentation --
none of these are redefined.

Objective outcomes (M1.38's `OutcomeMeasurement`) remain the sole truth
source used to validate a feedback signal (AC: "objective outcomes remain
the primary truth source") -- feedback itself is never treated as ground
truth, only as a hypothesis to be checked against it.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .discovery_effectiveness import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK
from .models import OutcomeMeasurement, Prediction, PredictionOutcome, RecommendationFeedback
from .outcome_measurement import OUTCOME_FAILURE, OUTCOME_SUCCESS
from .score_analysis import SCORE_BAND_COUNT, SCORE_BAND_WIDTH
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

FEEDBACK_LEARNING_SIGNAL_VERSION = "FLS-001"

# A prediction is a "repeated pattern" when at least this many distinct
# users independently gave the same (category, reason_code) feedback on it.
REPEATED_PATTERN_MIN_DISTINCT_USERS = 2


@dataclass(frozen=True)
class FeedbackSignal:
    category: str
    reason_code: str
    total_feedback_count: int
    distinct_prediction_count: int
    distinct_user_count: int
    repeated_prediction_count: int
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None
    verdict: str


@dataclass(frozen=True)
class FeedbackSegmentSignal:
    dimension: str
    key: str
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None
    verdict: str


@dataclass(frozen=True)
class FeedbackLearningSignalReport:
    version: str
    signals: tuple[FeedbackSignal, ...]
    by_horizon: tuple[FeedbackSegmentSignal, ...]
    by_model_version: tuple[FeedbackSegmentSignal, ...]
    by_score_band: tuple[FeedbackSegmentSignal, ...]


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _verdict(sample_count: int, success_rate: Decimal | None, overall_success_rate: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or success_rate is None or overall_success_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if overall_success_rate - success_rate >= WEAKNESS_MARGIN:
        return VERDICT_WEAK
    return VERDICT_OK


def _score_band(opportunity_score: Decimal) -> str:
    index = min(max(int(opportunity_score / SCORE_BAND_WIDTH), 0), SCORE_BAND_COUNT - 1)
    lower, upper = SCORE_BAND_WIDTH * index, SCORE_BAND_WIDTH * (index + 1)
    return f"[{lower}, {upper}{']' if index == SCORE_BAND_COUNT - 1 else ')'}"


def compute_feedback_learning_signals(session: Session) -> FeedbackLearningSignalReport:
    """Aggregates every feedback event against the prediction it was given
    on and that prediction's objective outcome, where one has closed (scope:
    "compare feedback with realized outcomes"). A prediction with multiple
    feedback events contributes to `evaluated_count`/`success_count` at most
    once per (category, reason_code) group, never once per raw feedback
    row, so a single vocal user cannot outweigh the sample count."""
    rows = session.execute(
        select(RecommendationFeedback, Prediction, PredictionOutcome, OutcomeMeasurement)
        .join(Prediction, Prediction.id == RecommendationFeedback.prediction_id)
        .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .outerjoin(OutcomeMeasurement, OutcomeMeasurement.prediction_outcome_id == PredictionOutcome.id)
    ).all()

    # Baseline success rate across every distinct, evaluated, feedback-linked
    # prediction -- the comparison point for each signal's own verdict.
    all_predictions_by_id: dict[int, Prediction] = {}
    all_classifications_by_prediction: dict[int, str] = {}
    for _feedback, prediction, _outcome, measurement in rows:
        all_predictions_by_id[prediction.id] = prediction
        if measurement is not None and measurement.outcome_classification in (OUTCOME_SUCCESS, OUTCOME_FAILURE):
            all_classifications_by_prediction[prediction.id] = measurement.outcome_classification
    overall_success_rate = _rate(
        sum(1 for c in all_classifications_by_prediction.values() if c == OUTCOME_SUCCESS),
        len(all_classifications_by_prediction),
    )

    groups: dict[tuple[str, str], dict] = {}
    for feedback, prediction, _outcome, _measurement in rows:
        key = (feedback.category, feedback.reason_code)
        bucket = groups.setdefault(
            key, dict(total=0, predictions=set(), users=set(), users_by_prediction={})
        )
        bucket["total"] += 1
        bucket["predictions"].add(prediction.id)
        bucket["users"].add(feedback.user_id)
        bucket["users_by_prediction"].setdefault(prediction.id, set()).add(feedback.user_id)

    signals = []
    for category, reason_code in sorted(groups):
        bucket = groups[(category, reason_code)]
        prediction_ids = bucket["predictions"]
        repeated = sum(
            1 for pid in prediction_ids if len(bucket["users_by_prediction"][pid]) >= REPEATED_PATTERN_MIN_DISTINCT_USERS
        )
        classifications = [all_classifications_by_prediction[pid] for pid in prediction_ids if pid in all_classifications_by_prediction]
        evaluated_count = len(classifications)
        success_count = sum(1 for c in classifications if c == OUTCOME_SUCCESS)
        success_rate = _rate(success_count, evaluated_count)

        signals.append(
            FeedbackSignal(
                category=category,
                reason_code=reason_code,
                total_feedback_count=bucket["total"],
                distinct_prediction_count=len(prediction_ids),
                distinct_user_count=len(bucket["users"]),
                repeated_prediction_count=repeated,
                evaluated_count=evaluated_count,
                success_count=success_count,
                success_rate=success_rate,
                verdict=_verdict(evaluated_count, success_rate, overall_success_rate),
            )
        )

    by_horizon = _segment_signals(
        "horizon", {str(p.horizon_days) for p in all_predictions_by_id.values()},
        lambda key: {pid for pid, p in all_predictions_by_id.items() if str(p.horizon_days) == key},
        all_classifications_by_prediction, overall_success_rate,
    )
    by_model_version = _segment_signals(
        "model_version", {p.model_version for p in all_predictions_by_id.values()},
        lambda key: {pid for pid, p in all_predictions_by_id.items() if p.model_version == key},
        all_classifications_by_prediction, overall_success_rate,
    )
    by_score_band = _segment_signals(
        "score_band", {_score_band(p.opportunity_score) for p in all_predictions_by_id.values()},
        lambda key: {pid for pid, p in all_predictions_by_id.items() if _score_band(p.opportunity_score) == key},
        all_classifications_by_prediction, overall_success_rate,
    )

    return FeedbackLearningSignalReport(
        version=FEEDBACK_LEARNING_SIGNAL_VERSION,
        signals=tuple(signals),
        by_horizon=by_horizon,
        by_model_version=by_model_version,
        by_score_band=by_score_band,
    )


def _segment_signals(dimension, keys, prediction_ids_for_key, classifications_by_prediction, overall_success_rate):
    result = []
    for key in sorted(keys):
        prediction_ids = prediction_ids_for_key(key)
        classifications = [classifications_by_prediction[pid] for pid in prediction_ids if pid in classifications_by_prediction]
        evaluated_count = len(classifications)
        success_count = sum(1 for c in classifications if c == OUTCOME_SUCCESS)
        success_rate = _rate(success_count, evaluated_count)
        result.append(
            FeedbackSegmentSignal(
                dimension=dimension,
                key=key,
                evaluated_count=evaluated_count,
                success_count=success_count,
                success_rate=success_rate,
                verdict=_verdict(evaluated_count, success_rate, overall_success_rate),
            )
        )
    return tuple(result)

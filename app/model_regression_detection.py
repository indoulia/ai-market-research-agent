"""EPIC-M1.67: detect when a promoted model's real-world recommendation
performance materially degrades relative to its own immutable, versioned
baseline window.

Reuses M1.25's `EvaluationWindow`/`OverlappingEvaluationWindowsError` (the
same disjoint-window abstraction M1.29/M1.30/M1.40/M1.41/M1.43/M1.49 already
use), M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON`, and M1.30's own
`REGRESSION_MARGIN` -- the same "is this drop large enough to be a real
regression, not noise" question, applied to one model's own before/after
real-world performance rather than a comparison between two models.

"Baseline is immutable and versioned" (AC) holds because the baseline
window and its measured success rate are frozen into the check row at the
moment of detection -- re-running a check with a different monitoring
window never alters a prior baseline measurement, only produces an
independent new row.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .candidate_model_evaluation import REGRESSION_MARGIN
from .market_regime import classify_market_regime
from .models import ModelRegressionCheck, Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate
from .out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

DETECTION_RULE_VERSION = "MRD-001"

VERDICT_HEALTHY = "HEALTHY"
VERDICT_REGRESSED = "REGRESSED"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    if a.end is not None and b.start is not None and a.end < b.start:
        return False
    if b.end is not None and a.start is not None and b.end < a.start:
        return False
    return True


def _evaluated_for_model_in_window(
    session: Session, model_version: str, window: EvaluationWindow
) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.execute(query).all())


def _segment_regressions(
    session: Session, baseline: list[tuple[Prediction, PredictionOutcome]], monitoring: list[tuple[Prediction, PredictionOutcome]]
) -> list[dict]:
    """Segments by horizon and regime, "where sample sizes permit" (scope)
    -- a segment below `MIN_SAMPLE_SIZE_FOR_COMPARISON` on either side is
    simply omitted, never used to draw an unsafe conclusion (AC: "small
    samples do not trigger unsafe conclusions")."""
    def _regime_for(prediction: Prediction) -> str | None:
        scan_id = session.execute(
            select(ScanCandidate.scan_id)
            .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
            .where(RecommendationGeneration.prediction_id == prediction.id)
        ).scalar_one_or_none()
        if scan_id is None:
            return None
        return classify_market_regime(session, scan_id).regime

    def _by_key(rows, key_fn):
        grouped: dict = {}
        for prediction, outcome in rows:
            grouped.setdefault(key_fn(prediction), []).append(outcome)
        return grouped

    regressions = []
    for dimension, key_fn in (
        ("horizon", lambda p: str(p.horizon_days)),
        ("regime", _regime_for),
    ):
        baseline_groups = _by_key(baseline, key_fn)
        monitoring_groups = _by_key(monitoring, key_fn)
        for key in sorted(set(baseline_groups) & set(monitoring_groups), key=str):
            if key is None:
                continue
            base_outcomes = baseline_groups[key]
            mon_outcomes = monitoring_groups[key]
            if len(base_outcomes) < MIN_SAMPLE_SIZE_FOR_COMPARISON or len(mon_outcomes) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
                continue
            base_rate = _rate(sum(1 for o in base_outcomes if o.outcome == "SUCCESS"), len(base_outcomes))
            mon_rate = _rate(sum(1 for o in mon_outcomes if o.outcome == "SUCCESS"), len(mon_outcomes))
            if base_rate is not None and mon_rate is not None and base_rate - mon_rate >= REGRESSION_MARGIN:
                regressions.append({
                    "dimension": dimension, "key": key,
                    "baseline_success_rate": str(base_rate), "monitoring_success_rate": str(mon_rate),
                })
    return regressions


def detect_model_regression(
    session: Session,
    *,
    model_version: str,
    baseline_window: EvaluationWindow,
    monitoring_window: EvaluationWindow,
    checked_at: datetime,
) -> ModelRegressionCheck:
    """Compares `model_version`'s own real-world success rate between two
    disjoint windows (AC: "baseline is immutable and versioned" -- frozen
    into this row at detection time). Raises `OverlappingEvaluationWindowsError`
    if the windows overlap -- monitoring must never reuse baseline evidence."""
    if _windows_overlap(baseline_window, monitoring_window):
        raise OverlappingEvaluationWindowsError(
            f"baseline window '{baseline_window.label}' and monitoring window '{monitoring_window.label}' overlap"
        )

    baseline_rows = _evaluated_for_model_in_window(session, model_version, baseline_window)
    monitoring_rows = _evaluated_for_model_in_window(session, model_version, monitoring_window)

    baseline_success = sum(1 for _, o in baseline_rows if o.outcome == "SUCCESS")
    monitoring_success = sum(1 for _, o in monitoring_rows if o.outcome == "SUCCESS")
    baseline_rate = _rate(baseline_success, len(baseline_rows))
    monitoring_rate = _rate(monitoring_success, len(monitoring_rows))

    if (
        len(baseline_rows) < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or len(monitoring_rows) < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or baseline_rate is None
        or monitoring_rate is None
    ):
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        segment_regressions: list = []
    elif baseline_rate - monitoring_rate >= REGRESSION_MARGIN:
        verdict = VERDICT_REGRESSED
        segment_regressions = _segment_regressions(session, baseline_rows, monitoring_rows)
    else:
        verdict = VERDICT_HEALTHY
        segment_regressions = _segment_regressions(session, baseline_rows, monitoring_rows)

    check = ModelRegressionCheck(
        model_version=model_version,
        baseline_window_label=baseline_window.label,
        baseline_success_rate=baseline_rate,
        baseline_sample_count=len(baseline_rows),
        monitoring_window_label=monitoring_window.label,
        monitoring_success_rate=monitoring_rate,
        monitoring_sample_count=len(monitoring_rows),
        verdict=verdict,
        segment_regressions=segment_regressions,
        rollback_triggered=(verdict == VERDICT_REGRESSED),
        checked_at=checked_at,
        detection_rule_version=DETECTION_RULE_VERSION,
    )
    session.add(check)
    session.commit()
    session.refresh(check)
    return check


def get_regression_history(session: Session, model_version: str) -> tuple[ModelRegressionCheck, ...]:
    return tuple(
        session.scalars(
            select(ModelRegressionCheck)
            .where(ModelRegressionCheck.model_version == model_version)
            .order_by(ModelRegressionCheck.id.asc())
        ).all()
    )

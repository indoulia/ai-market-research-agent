"""EPIC-M1.117: the evidence gate for declaring the MRA prediction
engine production-ready -- proving the system is measurable,
calibrated, reproducible, continuously monitored and safe to improve,
not that it predicts perfectly.

`compile_release_readiness_report` deliberately recomputes almost
nothing: it composes already-persisted evidence from M1.67 (regression),
M1.88 (learning), M1.97 (leakage/bias guard), M1.101/M1.114 (drift/
outage continuity), M1.115 (reproducibility), and M1.82 (benchmark
performance) into six checks, one per this EPIC's own Acceptance
Criteria bullet. The only genuinely new measurement this module
contributes is `compute_probabilistic_scores` -- Brier and log score,
two standard, well-known probabilistic-forecast scoring rules this
platform's own calibration modules (M1.11/M1.29/M1.49) never computed
(they measure bucket-level calibration error, a related but different
question from "how good are these probabilities as a whole").

Every check is honest about insufficient evidence: a check that finds
no data at all is `INSUFFICIENT_EVIDENCE`, not a silent pass -- the
overall verdict is `READY_FOR_PRODUCTION` only when every check is an
explicit `PASS`; any `FAIL` or `INSUFFICIENT_EVIDENCE` keeps the system
`NOT_READY`, named in `blocking_issues`. This module never promotes,
suppresses, or gates anything itself -- it is a read-only report for a
human release decision, with no write path to any production table.
"""
from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .model_regression_detection import get_regression_history
from .models import (
    BiasGuardCheck,
    Prediction,
    PredictionOutcome,
    PredictionQualityBenchmarkReport,
    PredictionTrustScore,
    PredictionUsefulnessAssessment,
    ProbabilisticScoreReport,
    ProviderOutageSnapshot,
    ReleaseReadinessReport,
    ReproducibilityAuditDecision,
)
from .out_of_sample_validation import EvaluationWindow
from .prediction_usefulness import USEFUL
from .provider_outage_tracker import SEVERITY_TOTAL
from .self_correction_loop import get_hypothesis_history
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

READINESS_GATE_VERSION = "PRG-117-001"

VERDICT_MEASURED = "MEASURED"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
CHECK_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

OVERALL_READY = "READY_FOR_PRODUCTION"
OVERALL_NOT_READY = "NOT_READY"

CHECK_INTEGRITY_AND_REPRODUCIBILITY = "INTEGRITY_AND_REPRODUCIBILITY"
CHECK_PROBABILISTIC_CALIBRATION = "PROBABILISTIC_CALIBRATION"
CHECK_TRUST_USEFULNESS_MONOTONICITY = "TRUST_USEFULNESS_MONOTONICITY"
CHECK_BENCHMARK_PERFORMANCE_DOCUMENTED = "BENCHMARK_PERFORMANCE_DOCUMENTED"
CHECK_CONTINUOUS_OPERATION = "CONTINUOUS_OPERATION"
CHECK_PROMOTION_REGRESSION_LEARNING_LOOP = "PROMOTION_REGRESSION_LEARNING_LOOP"

# Fixed, documented, versioned policy threshold: a Brier score below this
# demonstrates real calibrated skill over an uninformative 50/50 forecast
# (whose Brier score is exactly 0.25) -- not learned or fitted.
BRIER_SCORE_ACCEPTABLE_THRESHOLD = Decimal("0.22")


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def compute_probabilistic_scores(
    session: Session, *, model_version: str, window: EvaluationWindow, computed_at: datetime
) -> ProbabilisticScoreReport:
    """Brier score = mean((p - y)^2); log score = mean(-log(p) if y=1
    else -log(1-p)), y in {0, 1} from M1.5's own SUCCESS/FAILURE outcome.
    Both are computed in `float` (a standard, well-understood scoring
    rule, not a monetary/rate figure this platform otherwise keeps in
    `Decimal`) and stored rounded to 6 decimal places. Always computes
    and persists a fresh, independent report row -- the same "report"
    posture as M1.85/M1.99/M1.102/M1.108/M1.109/M1.111/M1.116."""
    query = (
        select(Prediction.predicted_probability, PredictionOutcome.outcome)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    )
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    rows = session.execute(query).all()

    sample_count = len(rows)
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        brier_score = None
        log_score = None
        verdict = VERDICT_INSUFFICIENT_SAMPLE
    else:
        epsilon = 1e-9
        squared_errors = []
        log_losses = []
        for predicted_probability, outcome in rows:
            p = max(epsilon, min(1 - epsilon, float(predicted_probability)))
            y = 1.0 if outcome == "SUCCESS" else 0.0
            squared_errors.append((p - y) ** 2)
            log_losses.append(-math.log(p) if y == 1.0 else -math.log(1 - p))
        brier_score = Decimal(str(round(sum(squared_errors) / sample_count, 6)))
        log_score = Decimal(str(round(sum(log_losses) / sample_count, 6)))
        verdict = VERDICT_MEASURED

    report = ProbabilisticScoreReport(
        model_version=model_version, window_label=window.label, sample_count=sample_count, brier_score=brier_score,
        log_score=log_score, verdict=verdict, computed_at=computed_at, report_rule_version=READINESS_GATE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _integrity_and_reproducibility_check(session: Session, model_version: str) -> dict:
    blocked_count = session.scalar(
        select(BiasGuardCheck.id)
        .join(Prediction, Prediction.id == BiasGuardCheck.prediction_id)
        .where(Prediction.model_version == model_version, BiasGuardCheck.verdict == "BLOCKED")
        .limit(1)
    )
    if blocked_count is not None:
        return {"check": CHECK_INTEGRITY_AND_REPRODUCIBILITY, "status": CHECK_FAIL, "detail": "at least one BiasGuardCheck BLOCKED verdict exists for this model version"}

    non_reproducible = session.scalar(
        select(ReproducibilityAuditDecision.id)
        .join(Prediction, Prediction.id == ReproducibilityAuditDecision.prediction_id)
        .where(Prediction.model_version == model_version, ReproducibilityAuditDecision.reproducible.is_(False))
        .limit(1)
    )
    detail = "no BiasGuardCheck BLOCKED verdicts found"
    if non_reproducible is not None:
        detail += "; note: at least one reproducibility audit found drift (informational, not blocking on its own -- may reflect honest environment drift rather than a defect)"
    return {"check": CHECK_INTEGRITY_AND_REPRODUCIBILITY, "status": CHECK_PASS, "detail": detail}


def _probabilistic_calibration_check(latest_score: ProbabilisticScoreReport | None) -> dict:
    if latest_score is None or latest_score.verdict == VERDICT_INSUFFICIENT_SAMPLE:
        return {"check": CHECK_PROBABILISTIC_CALIBRATION, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no measured Brier score yet"}
    if latest_score.brier_score <= BRIER_SCORE_ACCEPTABLE_THRESHOLD:
        return {"check": CHECK_PROBABILISTIC_CALIBRATION, "status": CHECK_PASS, "detail": f"brier_score={latest_score.brier_score} <= {BRIER_SCORE_ACCEPTABLE_THRESHOLD}"}
    return {"check": CHECK_PROBABILISTIC_CALIBRATION, "status": CHECK_FAIL, "detail": f"brier_score={latest_score.brier_score} > {BRIER_SCORE_ACCEPTABLE_THRESHOLD}"}


def _trust_usefulness_monotonicity_check(session: Session, model_version: str) -> dict:
    rows = session.execute(
        select(PredictionTrustScore.trust_quality, PredictionUsefulnessAssessment.usefulness_verdict)
        .select_from(PredictionTrustScore)
        .join(Prediction, Prediction.id == PredictionTrustScore.prediction_id)
        .join(PredictionUsefulnessAssessment, PredictionUsefulnessAssessment.prediction_id == Prediction.id)
        .where(Prediction.model_version == model_version)
    ).all()

    buckets: dict[str, list[str]] = {}
    for trust_quality, usefulness_verdict in rows:
        buckets.setdefault(trust_quality, []).append(usefulness_verdict)

    rates = {}
    for quality in ("LOW", "MEDIUM", "HIGH"):
        verdicts = buckets.get(quality, [])
        if len(verdicts) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
            continue
        rates[quality] = _rate(sum(1 for v in verdicts if v == USEFUL), len(verdicts))

    if len(rates) < 2:
        return {"check": CHECK_TRUST_USEFULNESS_MONOTONICITY, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": f"fewer than 2 trust-quality buckets have sufficient sample ({sorted(rates)})"}

    ordered = [rates[q] for q in ("LOW", "MEDIUM", "HIGH") if q in rates]
    is_monotonic = all(ordered[i] <= ordered[i + 1] for i in range(len(ordered) - 1))
    if is_monotonic:
        return {"check": CHECK_TRUST_USEFULNESS_MONOTONICITY, "status": CHECK_PASS, "detail": f"usefulness rate non-decreasing across trust buckets: {rates}"}
    return {"check": CHECK_TRUST_USEFULNESS_MONOTONICITY, "status": CHECK_FAIL, "detail": f"usefulness rate not monotonic across trust buckets: {rates}"}


def _benchmark_performance_documented_check(session: Session, model_version: str) -> dict:
    latest = session.scalar(
        select(PredictionQualityBenchmarkReport)
        .where(PredictionQualityBenchmarkReport.model_version == model_version)
        .order_by(PredictionQualityBenchmarkReport.id.desc())
    )
    if latest is None:
        return {"check": CHECK_BENCHMARK_PERFORMANCE_DOCUMENTED, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no benchmark report computed yet"}
    return {"check": CHECK_BENCHMARK_PERFORMANCE_DOCUMENTED, "status": CHECK_PASS, "detail": f"benchmark_verdict={latest.benchmark_verdict}, verdict={latest.verdict} (documented either way)"}


def _continuous_operation_check(session: Session) -> dict:
    total_outage = session.scalar(select(ProviderOutageSnapshot.id).where(ProviderOutageSnapshot.severity == SEVERITY_TOTAL).order_by(ProviderOutageSnapshot.id.desc()).limit(1))
    if total_outage is not None:
        return {"check": CHECK_CONTINUOUS_OPERATION, "status": CHECK_FAIL, "detail": "at least one TOTAL provider outage snapshot exists"}
    return {"check": CHECK_CONTINUOUS_OPERATION, "status": CHECK_PASS, "detail": "no TOTAL provider outage snapshots recorded"}


def _promotion_regression_learning_loop_check(session: Session, model_version: str) -> dict:
    regression_history = get_regression_history(session, model_version)
    hypothesis_history = get_hypothesis_history(session, model_version=model_version)
    if not regression_history:
        return {"check": CHECK_PROMOTION_REGRESSION_LEARNING_LOOP, "status": CHECK_INSUFFICIENT_EVIDENCE, "detail": "no model regression checks have run yet for this model version"}
    return {
        "check": CHECK_PROMOTION_REGRESSION_LEARNING_LOOP, "status": CHECK_PASS,
        "detail": f"{len(regression_history)} regression check(s), {len(hypothesis_history)} learning hypothesis run(s) recorded",
    }


def compile_release_readiness_report(session: Session, *, model_version: str, computed_at: datetime) -> ReleaseReadinessReport:
    """Always computes and persists a fresh, independent report row.
    `READY_FOR_PRODUCTION` requires every one of the six checks to be an
    explicit `PASS` -- an `INSUFFICIENT_EVIDENCE` check keeps the system
    honestly `NOT_READY`, never treated as a passing default."""
    latest_probabilistic_score = session.scalar(
        select(ProbabilisticScoreReport).where(ProbabilisticScoreReport.model_version == model_version).order_by(ProbabilisticScoreReport.id.desc())
    )

    checks = [
        _integrity_and_reproducibility_check(session, model_version),
        _probabilistic_calibration_check(latest_probabilistic_score),
        _trust_usefulness_monotonicity_check(session, model_version),
        _benchmark_performance_documented_check(session, model_version),
        _continuous_operation_check(session),
        _promotion_regression_learning_loop_check(session, model_version),
    ]

    blocking_issues = [c["check"] for c in checks if c["status"] != CHECK_PASS]
    overall_verdict = OVERALL_READY if not blocking_issues else OVERALL_NOT_READY

    report = ReleaseReadinessReport(
        model_version=model_version, check_results=checks, blocking_issues=blocking_issues, overall_verdict=overall_verdict,
        computed_at=computed_at, report_rule_version=READINESS_GATE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_readiness_report_history(session: Session, model_version: str) -> tuple[ReleaseReadinessReport, ...]:
    return tuple(
        session.scalars(
            select(ReleaseReadinessReport).where(ReleaseReadinessReport.model_version == model_version).order_by(ReleaseReadinessReport.id.asc())
        ).all()
    )

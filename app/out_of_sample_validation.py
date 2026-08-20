"""EPIC-M1.25: the evidence gate for all downstream learning EPICs (M1.26+).
Validates recommendation behavior on a strictly time-bounded, out-of-sample
evaluation window -- never mixing it with a separate baseline window -- and
compares a candidate window's success rate against a baseline's, refusing to
call a candidate "validated" without enough out-of-sample evidence on both
sides.

This repo does not yet have a second, real candidate model to compare against
a production one (that is future scope for the model-evaluation EPICs M1.26+
themselves unblock). What IS buildable now, and genuinely useful today, is a
generic time-window comparison: any two disjoint, explicitly-bounded periods
of already-evaluated recommendations can be compared, whether "baseline" and
"candidate" mean two eras of the same code, a period before/after a deploy, or
(once a real second model exists) two different models' recommendations. The
comparison logic itself does not care which.

Regime/sector/market-cap segmentation is deliberately deferred here for the
same reason M1.23 deferred it: market regime detection isn't implemented, and
`DiscoverySegment` (M1.34) only covers candidates that were explicitly
segmented, not every historical `Prediction` -- reporting on it today would
silently under-represent most history rather than being real, complete
evidence. Discovery-source segmentation (scope item 5's "discovery source"),
by contrast, is fully implemented, since M1.17/M1.19/M1.33 all record
`DiscoveryRecord` provenance for their entire respective paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DiscoveryRecord, Prediction, PredictionOutcome, RecommendationGeneration
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

OOS_VALIDATION_VERSION = "OOS-001"

VERDICT_VALIDATED = "VALIDATED"
VERDICT_REGRESSED = "REGRESSED"
VERDICT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

# A candidate window's success rate falling this far below the baseline's,
# with sufficient samples on both sides, is a regression rather than noise.
# Fixed, documented, versioned policy constant.
REGRESSION_MARGIN = Decimal("0.10")


class OverlappingEvaluationWindowsError(RuntimeError):
    """Raised when a baseline and candidate window overlap -- comparing a
    candidate against a baseline that shares some of its own evidence is not
    a real out-of-sample comparison."""


@dataclass(frozen=True)
class EvaluationWindow:
    label: str
    start: datetime | None
    end: datetime | None


@dataclass(frozen=True)
class DiscoverySourceMetric:
    source: str
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None


@dataclass(frozen=True)
class OutOfSampleReport:
    report_version: str
    window: EvaluationWindow
    evaluated_count: int
    success_count: int
    failure_count: int
    success_rate: Decimal | None
    by_discovery_source: tuple[DiscoverySourceMetric, ...]
    verdict: str


@dataclass(frozen=True)
class ComparisonResult:
    report_version: str
    baseline: OutOfSampleReport
    candidate: OutOfSampleReport
    success_rate_delta: Decimal | None
    verdict: str


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    a_start = a.start
    a_end = a.end
    b_start = b.start
    b_end = b.end
    if a_end is not None and b_start is not None and a_end < b_start:
        return False
    if b_end is not None and a_start is not None and b_end < a_start:
        return False
    return True


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _evaluated_predictions_in_window(
    session: Session, window: EvaluationWindow
) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.execute(query).all())


def _discovery_source_breakdown(
    session: Session, evaluated: list[tuple[Prediction, PredictionOutcome]]
) -> tuple[DiscoverySourceMetric, ...]:
    if not evaluated:
        return ()

    prediction_ids = [p.id for p, _ in evaluated]
    outcome_by_prediction_id = {p.id: o for p, o in evaluated}
    source_rows = session.execute(
        select(RecommendationGeneration.prediction_id, DiscoveryRecord.source)
        .join(DiscoveryRecord, DiscoveryRecord.recommendation_generation_id == RecommendationGeneration.id)
        .where(RecommendationGeneration.prediction_id.in_(prediction_ids))
    ).all()

    by_source: dict[str, list[PredictionOutcome]] = {}
    for prediction_id, source in source_rows:
        by_source.setdefault(source, []).append(outcome_by_prediction_id[prediction_id])

    metrics = []
    for source in sorted(by_source):
        outcomes = by_source[source]
        success_count = sum(1 for o in outcomes if o.outcome == "SUCCESS")
        metrics.append(
            DiscoverySourceMetric(
                source=source,
                evaluated_count=len(outcomes),
                success_count=success_count,
                success_rate=_rate(success_count, len(outcomes)),
            )
        )
    return tuple(metrics)


def compute_out_of_sample_report(session: Session, window: EvaluationWindow) -> OutOfSampleReport:
    """Every statistic is computed only from recommendations whose
    `as_of_timestamp` falls inside `window` -- no data outside the window's
    bounds is ever queried (scope item 2: "no future information leaks into
    historical evaluation" holds by construction, the same pattern M1.24 uses
    for point-in-time safety)."""
    evaluated = _evaluated_predictions_in_window(session, window)
    success_count = sum(1 for _, o in evaluated if o.outcome == "SUCCESS")
    failure_count = sum(1 for _, o in evaluated if o.outcome == "FAILURE")
    success_rate = _rate(success_count, len(evaluated))

    verdict = VERDICT_INSUFFICIENT_EVIDENCE if len(evaluated) < MIN_SAMPLE_SIZE_FOR_COMPARISON else VERDICT_VALIDATED

    return OutOfSampleReport(
        report_version=OOS_VALIDATION_VERSION,
        window=window,
        evaluated_count=len(evaluated),
        success_count=success_count,
        failure_count=failure_count,
        success_rate=success_rate,
        by_discovery_source=_discovery_source_breakdown(session, evaluated),
        verdict=verdict,
    )


def compare_out_of_sample_windows(
    session: Session, *, baseline: EvaluationWindow, candidate: EvaluationWindow
) -> ComparisonResult:
    """Compare a candidate window's success rate against a baseline's.
    Raises `OverlappingEvaluationWindowsError` if the two windows overlap --
    a real out-of-sample comparison requires disjoint evidence. Never
    declares a candidate `VALIDATED` without both windows individually
    clearing the minimum-sample floor (scope item 8: "reject or mark
    insufficient any candidate without adequate out-of-sample evidence")."""
    if _windows_overlap(baseline, candidate):
        raise OverlappingEvaluationWindowsError(
            f"baseline window '{baseline.label}' and candidate window '{candidate.label}' overlap"
        )

    baseline_report = compute_out_of_sample_report(session, baseline)
    candidate_report = compute_out_of_sample_report(session, candidate)

    if (
        baseline_report.verdict == VERDICT_INSUFFICIENT_EVIDENCE
        or candidate_report.verdict == VERDICT_INSUFFICIENT_EVIDENCE
    ):
        return ComparisonResult(
            report_version=OOS_VALIDATION_VERSION,
            baseline=baseline_report,
            candidate=candidate_report,
            success_rate_delta=None,
            verdict=VERDICT_INSUFFICIENT_EVIDENCE,
        )

    delta = candidate_report.success_rate - baseline_report.success_rate
    verdict = VERDICT_REGRESSED if delta <= -REGRESSION_MARGIN else VERDICT_VALIDATED

    return ComparisonResult(
        report_version=OOS_VALIDATION_VERSION,
        baseline=baseline_report,
        candidate=candidate_report,
        success_rate_delta=delta,
        verdict=verdict,
    )

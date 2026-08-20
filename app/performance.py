"""EPIC-M1.6: report the historical performance of positive recommendations from
objectively evaluated outcomes only (M1.5). Every statistic here is a plain
deterministic aggregate over stored `Prediction`/`PredictionOutcome` rows -- no LLM
reasoning, no model retraining, and no cherry-picking: failed recommendations remain
just as visible as successful ones.
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome
from .recommendations import VALID_HORIZON_DAYS

REPORT_VERSION = "PERF-001"

# Fixed-width probability buckets covering the full [0, 1] range; always reported
# (even empty) so no bucket is silently omitted. The last bucket is closed on both
# ends so predicted_probability == 1 has a home.
PROBABILITY_BUCKET_COUNT = 10
PROBABILITY_BUCKET_WIDTH = Decimal("1") / PROBABILITY_BUCKET_COUNT


@dataclass(frozen=True)
class HorizonPerformance:
    horizon_days: int
    evaluated_count: int
    success_count: int
    failure_count: int
    success_rate: Decimal | None


@dataclass(frozen=True)
class ProbabilityBucketPerformance:
    bucket_label: str
    lower: Decimal
    upper: Decimal
    evaluated_count: int
    success_count: int
    failure_count: int
    success_rate: Decimal | None


@dataclass(frozen=True)
class ReturnPerformance:
    evaluated_count: int
    average_predicted_return: Decimal | None
    average_actual_return: Decimal | None
    winning_count: int
    average_winning_return: Decimal | None
    losing_count: int
    average_losing_return: Decimal | None


@dataclass(frozen=True)
class PerformanceReport:
    report_version: str
    total_recommendations: int
    open_count: int
    unevaluable_count: int
    evaluated_count: int
    success_count: int
    failure_count: int
    overall_success_rate: Decimal | None
    by_horizon: tuple[HorizonPerformance, ...]
    by_probability_bucket: tuple[ProbabilityBucketPerformance, ...]
    returns: ReturnPerformance


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _bucket_index(predicted_probability: Decimal) -> int:
    index = int(predicted_probability / PROBABILITY_BUCKET_WIDTH)
    return min(index, PROBABILITY_BUCKET_COUNT - 1)


def _horizon_breakdown(evaluated: list[tuple[Prediction, PredictionOutcome]]) -> tuple[HorizonPerformance, ...]:
    breakdown = []
    for horizon_days in VALID_HORIZON_DAYS:
        subset = [(p, o) for p, o in evaluated if p.horizon_days == horizon_days]
        success_count = sum(1 for _, o in subset if o.outcome == "SUCCESS")
        failure_count = sum(1 for _, o in subset if o.outcome == "FAILURE")
        breakdown.append(HorizonPerformance(
            horizon_days=horizon_days,
            evaluated_count=len(subset),
            success_count=success_count,
            failure_count=failure_count,
            success_rate=_rate(success_count, len(subset)),
        ))
    return tuple(breakdown)


def _probability_bucket_breakdown(evaluated: list[tuple[Prediction, PredictionOutcome]]) -> tuple[ProbabilityBucketPerformance, ...]:
    buckets = []
    for index in range(PROBABILITY_BUCKET_COUNT):
        lower = PROBABILITY_BUCKET_WIDTH * index
        upper = PROBABILITY_BUCKET_WIDTH * (index + 1)
        subset = [(p, o) for p, o in evaluated if _bucket_index(p.predicted_probability) == index]
        success_count = sum(1 for _, o in subset if o.outcome == "SUCCESS")
        failure_count = sum(1 for _, o in subset if o.outcome == "FAILURE")
        buckets.append(ProbabilityBucketPerformance(
            bucket_label=f"[{lower}, {upper}{']' if index == PROBABILITY_BUCKET_COUNT - 1 else ')'}",
            lower=lower,
            upper=upper,
            evaluated_count=len(subset),
            success_count=success_count,
            failure_count=failure_count,
            success_rate=_rate(success_count, len(subset)),
        ))
    return tuple(buckets)


def _return_breakdown(evaluated: list[tuple[Prediction, PredictionOutcome]]) -> ReturnPerformance:
    winning = [o.actual_return for _, o in evaluated if o.outcome == "SUCCESS"]
    losing = [o.actual_return for _, o in evaluated if o.outcome == "FAILURE"]
    return ReturnPerformance(
        evaluated_count=len(evaluated),
        average_predicted_return=_mean([p.target_return for p, _ in evaluated]),
        average_actual_return=_mean([o.actual_return for _, o in evaluated]),
        winning_count=len(winning),
        average_winning_return=_mean(winning),
        losing_count=len(losing),
        average_losing_return=_mean(losing),
    )


def compute_performance_report(session: Session) -> PerformanceReport:
    """Every percentage here always carries its underlying sample count (AC), and
    UNEVALUABLE / still-OPEN recommendations are excluded from the success-rate
    denominator but still counted and reported separately (AC), never silently
    dropped."""
    rows = session.execute(
        select(Prediction, PredictionOutcome)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id, isouter=True)
    ).all()

    open_count = 0
    unevaluable_count = 0
    evaluated: list[tuple[Prediction, PredictionOutcome]] = []
    for prediction, outcome in rows:
        if outcome is None:
            open_count += 1
        elif outcome.outcome == "UNEVALUABLE":
            unevaluable_count += 1
        else:
            evaluated.append((prediction, outcome))

    success_count = sum(1 for _, o in evaluated if o.outcome == "SUCCESS")
    failure_count = sum(1 for _, o in evaluated if o.outcome == "FAILURE")

    return PerformanceReport(
        report_version=REPORT_VERSION,
        total_recommendations=len(rows),
        open_count=open_count,
        unevaluable_count=unevaluable_count,
        evaluated_count=len(evaluated),
        success_count=success_count,
        failure_count=failure_count,
        overall_success_rate=_rate(success_count, len(evaluated)),
        by_horizon=_horizon_breakdown(evaluated),
        by_probability_bucket=_probability_bucket_breakdown(evaluated),
        returns=_return_breakdown(evaluated),
    )

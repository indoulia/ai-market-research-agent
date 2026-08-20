"""EPIC-M1.22: measure whether M1.9's opportunity score is predictive of
realized M1.5 outcomes, producing deterministic, versioned evidence that a
later, separately-approved score-adjustment EPIC can safely consume. This
module never writes to `Prediction.opportunity_score` or any other production
value -- it is read-only analysis, exactly like M1.6's performance report and
M1.16's trust report.

Reuses M1.16's weak/insufficient-sample verdict policy constants
(`MIN_SAMPLE_SIZE_FOR_COMPARISON`, `WEAKNESS_MARGIN`) rather than inventing a
second threshold for the same underlying question ("is this segment reliable
evidence?") -- score bands are just another segment dimension alongside
M1.16's horizons and probability buckets.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome
from .recommendations import VALID_HORIZON_DAYS
from .trust_report import (
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OK,
    VERDICT_WEAK,
    WEAKNESS_MARGIN,
)

SCORE_ANALYSIS_VERSION = "SCA-001"

# Fixed-width score bands covering the full [0, 100] `opportunity_score` range
# (M1.9), mirroring M1.6's ten fixed-width probability buckets. Always all ten
# reported, even empty, so no band is silently omitted.
SCORE_BAND_COUNT = 10
SCORE_BAND_WIDTH = Decimal("10")


@dataclass(frozen=True)
class ScoreBandPerformance:
    band_label: str
    lower: Decimal
    upper: Decimal
    evaluated_count: int
    success_count: int
    failure_count: int
    success_rate: Decimal | None


@dataclass(frozen=True)
class ScoreBandTrust:
    band: ScoreBandPerformance
    verdict: str


@dataclass(frozen=True)
class HorizonScoreBreakdown:
    horizon_days: int
    bands: tuple[ScoreBandTrust, ...]


@dataclass(frozen=True)
class ScoreAnalysisReport:
    report_version: str
    total_recommendations: int
    open_count: int
    unevaluable_count: int
    evaluated_count: int
    overall_success_rate: Decimal | None
    overall_bands: tuple[ScoreBandTrust, ...]
    by_horizon: tuple[HorizonScoreBreakdown, ...]


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _band_index(score: Decimal) -> int:
    index = int(score / SCORE_BAND_WIDTH)
    return min(max(index, 0), SCORE_BAND_COUNT - 1)


def _score_band_breakdown(evaluated: list[tuple[Prediction, PredictionOutcome]]) -> tuple[ScoreBandPerformance, ...]:
    bands = []
    for index in range(SCORE_BAND_COUNT):
        lower = SCORE_BAND_WIDTH * index
        upper = SCORE_BAND_WIDTH * (index + 1)
        subset = [(p, o) for p, o in evaluated if _band_index(p.opportunity_score) == index]
        success_count = sum(1 for _, o in subset if o.outcome == "SUCCESS")
        failure_count = sum(1 for _, o in subset if o.outcome == "FAILURE")
        bands.append(
            ScoreBandPerformance(
                band_label=f"[{lower}, {upper}{']' if index == SCORE_BAND_COUNT - 1 else ')'}",
                lower=lower,
                upper=upper,
                evaluated_count=len(subset),
                success_count=success_count,
                failure_count=failure_count,
                success_rate=_rate(success_count, len(subset)),
            )
        )
    return tuple(bands)


def _verdict(sample_count: int, success_rate: Decimal | None, overall_success_rate: Decimal | None) -> str:
    """Identical policy to `app.trust_report`'s verdict rule (scope item 5:
    "identify statistically weak or insufficient score bands") -- reuses the
    same fixed thresholds rather than a second, independently-tunable one."""
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or success_rate is None or overall_success_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if overall_success_rate - success_rate >= WEAKNESS_MARGIN:
        return VERDICT_WEAK
    return VERDICT_OK


def _trust_bands(
    bands: tuple[ScoreBandPerformance, ...], overall_success_rate: Decimal | None
) -> tuple[ScoreBandTrust, ...]:
    return tuple(
        ScoreBandTrust(band=band, verdict=_verdict(band.evaluated_count, band.success_rate, overall_success_rate))
        for band in bands
    )


def compute_score_analysis_report(session: Session) -> ScoreAnalysisReport:
    """Every statistic here is a plain deterministic aggregate over stored
    `Prediction`/`PredictionOutcome` rows (scope item 6) -- no LLM reasoning,
    and no write path to any production score (scope item 7). `open`/
    `unevaluable` recommendations are excluded from success-rate denominators
    but still counted and reported (scope item 4), mirroring M1.6."""
    rows = session.execute(
        select(Prediction, PredictionOutcome).join(
            PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id, isouter=True
        )
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
    overall_success_rate = _rate(success_count, len(evaluated))

    overall_bands = _trust_bands(_score_band_breakdown(evaluated), overall_success_rate)

    by_horizon = tuple(
        HorizonScoreBreakdown(
            horizon_days=horizon_days,
            bands=_trust_bands(
                _score_band_breakdown([(p, o) for p, o in evaluated if p.horizon_days == horizon_days]),
                overall_success_rate,
            ),
        )
        for horizon_days in VALID_HORIZON_DAYS
    )

    return ScoreAnalysisReport(
        report_version=SCORE_ANALYSIS_VERSION,
        total_recommendations=len(rows),
        open_count=open_count,
        unevaluable_count=unevaluable_count,
        evaluated_count=len(evaluated),
        overall_success_rate=overall_success_rate,
        overall_bands=overall_bands,
        by_horizon=by_horizon,
    )

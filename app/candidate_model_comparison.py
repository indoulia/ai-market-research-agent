"""EPIC-M1.43: compare a candidate prediction/scoring model against the
current production model using identical historical evaluation rules --
running both models on the exact same point-in-time dataset, rather than
M1.30's "same model, two disjoint time periods" comparison.

A "model" here is a plain function `HistoricalLearningRecord -> Decimal`
returning an implied success probability from that record's own frozen,
point-in-time-safe feature columns (M1.39) -- the comparable model interface
this EPIC's scope calls for. `production_model` is always the historical
pipeline's own recorded `predicted_probability`, exactly as it was computed
at the time (no recomputation, so no leakage risk is introduced). This repo
still has no second, real production-quality candidate model -- the same
honest caveat M1.25/M1.29/M1.30/M1.40 already documented -- but the
comparison machinery itself is genuinely usable today with any candidate
callable a caller supplies.

Composes rather than duplicates: M1.39's `HistoricalLearningRecord` dataset
is the single common point-in-time input both models see (AC: "both models
receive identical eligible inputs"); M1.41's on-demand `classify_market_regime`
technique is reused so regime segmentation reaches full coverage rather than
"where available"; M1.30's `VERDICT_VALIDATED`/`VERDICT_REGRESSED`/
`VERDICT_INSUFFICIENT_EVIDENCE`/`REGRESSION_MARGIN` vocabulary is reused
unchanged; M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON` gates every dimension.

Read-only; never promotes any candidate into production (AC: "candidate is
not promoted by this EPIC" -- there is no write path in this module at all).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .candidate_model_evaluation import REGRESSION_MARGIN, VERDICT_INSUFFICIENT_EVIDENCE, VERDICT_REGRESSED, VERDICT_VALIDATED
from .historical_learning_dataset import build_learning_dataset, get_learning_dataset
from .market_regime import classify_market_regime
from .models import HistoricalLearningRecord, RecommendationGeneration, ScanCandidate
from .outcome_measurement import OUTCOME_FAILURE, OUTCOME_SUCCESS
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

CANDIDATE_MODEL_COMPARISON_VERSION = "CMC-001"

ModelFunction = Callable[[HistoricalLearningRecord], Decimal]


def production_model(record: HistoricalLearningRecord) -> Decimal:
    """The historical pipeline's own recorded probability -- never
    recomputed, so it carries zero leakage risk beyond what M1.39 already
    guarantees."""
    return record.predicted_probability


@dataclass(frozen=True)
class ModelSegmentMetric:
    dimension: str
    key: str
    evaluated_count: int
    average_predicted_probability: Decimal | None
    observed_success_rate: Decimal | None
    mean_absolute_calibration_error: Decimal | None


@dataclass(frozen=True)
class ModelEvaluation:
    model_name: str
    evaluated_count: int
    observed_success_rate: Decimal | None
    average_predicted_probability: Decimal | None
    average_realized_return: Decimal | None
    mean_absolute_calibration_error: Decimal | None
    by_horizon: tuple[ModelSegmentMetric, ...]
    by_sector: tuple[ModelSegmentMetric, ...]
    by_market_cap_bucket: tuple[ModelSegmentMetric, ...]
    by_discovery_source: tuple[ModelSegmentMetric, ...]
    by_regime: tuple[ModelSegmentMetric, ...]
    insufficient_sample_dimensions: tuple[str, ...]


@dataclass(frozen=True)
class CandidateModelComparisonReport:
    version: str
    dataset_version: str
    production: ModelEvaluation
    candidate: ModelEvaluation
    calibration_error_delta: Decimal | None
    verdict: str


def _mean(values: list) -> Decimal | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _regime_for_record(session: Session, record: HistoricalLearningRecord, cache: dict) -> str | None:
    """Reuses M1.41's on-demand classification technique: every record's
    prediction traces to the eligible `ScanCandidate` it was generated from,
    so classification always succeeds -- full regime coverage rather than a
    'where available' fallback, even for a record whose frozen
    `market_regime` column happened to be null at dataset-build time."""
    if record.market_regime is not None:
        return record.market_regime
    if record.prediction_id in cache:
        return cache[record.prediction_id]
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == record.prediction_id)
    ).scalar_one_or_none()
    regime = None if scan_id is None else classify_market_regime(session, scan_id).regime
    cache[record.prediction_id] = regime
    return regime


def _bucket(dimension: str, key: str, pairs: list[tuple[Decimal, Decimal]]) -> ModelSegmentMetric:
    success = sum(1 for _, actual in pairs if actual == Decimal("1"))
    return ModelSegmentMetric(
        dimension=dimension,
        key=key,
        evaluated_count=len(pairs),
        average_predicted_probability=_mean([p for p, _ in pairs]),
        observed_success_rate=_rate(success, len(pairs)),
        mean_absolute_calibration_error=_mean([abs(p - a) for p, a in pairs]),
    )


def _group_and_bucket(dimension: str, grouped: dict[str, list]) -> tuple[ModelSegmentMetric, ...]:
    return tuple(_bucket(dimension, key, grouped[key]) for key in sorted(grouped))


def _evaluate_model(
    session: Session, records: tuple[HistoricalLearningRecord, ...], model: ModelFunction, model_name: str
) -> ModelEvaluation:
    """Runs `model` over the identical set of `records` used for every other
    model in this comparison (AC: "both models receive identical eligible
    inputs"; "metrics use identical outcome definitions" -- SUCCESS/FAILURE
    only, the same definition every other comparison EPIC in this platform
    uses). No feature outside `record`'s own frozen columns is ever read, so
    no future information can leak into `model` (AC)."""
    rows = []
    regime_cache: dict = {}
    for record in records:
        if record.outcome_classification not in (OUTCOME_SUCCESS, OUTCOME_FAILURE):
            continue
        predicted = model(record)
        actual = Decimal("1") if record.outcome_classification == OUTCOME_SUCCESS else Decimal("0")
        rows.append((record, predicted, actual))

    evaluated_count = len(rows)
    success_count = sum(1 for _, _, a in rows if a == Decimal("1"))
    average_predicted = _mean([p for _, p, _ in rows])
    average_return = _mean([r.realized_return for r, _, _ in rows])
    mae = _mean([abs(p - a) for _, p, a in rows])

    by_horizon_groups: dict[str, list] = {}
    by_sector_groups: dict[str, list] = {}
    by_cap_groups: dict[str, list] = {}
    by_source_groups: dict[str, list] = {}
    by_regime_groups: dict[str, list] = {}
    for record, predicted, actual in rows:
        by_horizon_groups.setdefault(str(record.horizon_days), []).append((predicted, actual))
        if record.sector is not None:
            by_sector_groups.setdefault(record.sector, []).append((predicted, actual))
        if record.market_cap_bucket is not None:
            by_cap_groups.setdefault(record.market_cap_bucket, []).append((predicted, actual))
        if record.discovery_source is not None:
            by_source_groups.setdefault(record.discovery_source, []).append((predicted, actual))
        regime = _regime_for_record(session, record, regime_cache)
        if regime is not None:
            by_regime_groups.setdefault(regime, []).append((predicted, actual))

    by_horizon = _group_and_bucket("horizon", by_horizon_groups)
    by_sector = _group_and_bucket("sector", by_sector_groups)
    by_market_cap_bucket = _group_and_bucket("market_cap_bucket", by_cap_groups)
    by_discovery_source = _group_and_bucket("discovery_source", by_source_groups)
    by_regime = _group_and_bucket("regime", by_regime_groups)

    insufficient = []
    if evaluated_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        insufficient.append("overall")
    for group in (by_horizon, by_sector, by_market_cap_bucket, by_discovery_source, by_regime):
        for metric in group:
            if 0 < metric.evaluated_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
                insufficient.append(f"{metric.dimension}:{metric.key}")

    return ModelEvaluation(
        model_name=model_name,
        evaluated_count=evaluated_count,
        observed_success_rate=_rate(success_count, evaluated_count),
        average_predicted_probability=average_predicted,
        average_realized_return=average_return,
        mean_absolute_calibration_error=mae,
        by_horizon=by_horizon,
        by_sector=by_sector,
        by_market_cap_bucket=by_market_cap_bucket,
        by_discovery_source=by_discovery_source,
        by_regime=by_regime,
        insufficient_sample_dimensions=tuple(insufficient),
    )


def compare_candidate_model(
    session: Session,
    *,
    dataset_version: str,
    candidate_model: ModelFunction,
    candidate_model_name: str = "candidate",
) -> CandidateModelComparisonReport:
    """Builds (or reuses) M1.39's dataset for `dataset_version`, then
    evaluates `production_model` and `candidate_model` over the exact same
    completed, included records -- the single common point-in-time dataset
    both models run against (AC: "both models receive identical eligible
    inputs"). Never writes anything; the candidate is never promoted (AC)."""
    build_learning_dataset(session, dataset_version=dataset_version)
    records = tuple(r for r in get_learning_dataset(session, dataset_version) if r.included)

    production_eval = _evaluate_model(session, records, production_model, "production")
    candidate_eval = _evaluate_model(session, records, candidate_model, candidate_model_name)

    if (
        "overall" in production_eval.insufficient_sample_dimensions
        or "overall" in candidate_eval.insufficient_sample_dimensions
    ):
        return CandidateModelComparisonReport(
            version=CANDIDATE_MODEL_COMPARISON_VERSION,
            dataset_version=dataset_version,
            production=production_eval,
            candidate=candidate_eval,
            calibration_error_delta=None,
            verdict=VERDICT_INSUFFICIENT_EVIDENCE,
        )

    delta = candidate_eval.mean_absolute_calibration_error - production_eval.mean_absolute_calibration_error
    verdict = VERDICT_REGRESSED if delta >= REGRESSION_MARGIN else VERDICT_VALIDATED

    return CandidateModelComparisonReport(
        version=CANDIDATE_MODEL_COMPARISON_VERSION,
        dataset_version=dataset_version,
        production=production_eval,
        candidate=candidate_eval,
        calibration_error_delta=delta,
        verdict=verdict,
    )

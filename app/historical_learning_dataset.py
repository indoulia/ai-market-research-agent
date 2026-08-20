"""EPIC-M1.39: turn completed recommendation history into a clean, point-in-
time-safe learning dataset -- one immutable row per `(dataset_version,
prediction_id)`, joining recommendation-time features to the finalized
outcome label plus whatever segment context (regime, sector, market-cap,
discovery source) is available for that recommendation.

Feature/label separation is the core leakage control (AC: "no post-
recommendation information enters features"): every feature column
(`predicted_probability`, `opportunity_score`, `sma20_distance`,
`volume_ratio_20d`, `atr_percent`) is copied from `Prediction`/`ScanCandidate`
-- values already computed only from information available as of
`Prediction.as_of_timestamp` (M1.12/M1.13's own point-in-time safety, unchanged
here). The label (`outcome_classification`, `realized_return`) comes from
M1.38's `OutcomeMeasurement`, which by definition only exists after the
horizon window has closed -- it is never treated as a feature, only as the
target this dataset exists to explain.

Composes rather than duplicates: regime via M1.26's `MarketRegime`, sector/
market-cap via M1.34's `DiscoverySegment`, discovery source via M1.17's
`DiscoveryRecord`, outcome label via M1.38's `OutcomeMeasurement` -- all
"where available," the same honest-partial-coverage pattern this platform
uses consistently (M1.23/M1.25/M1.27/M1.28/M1.29/M1.30). A prediction whose
outcome measurement doesn't exist yet, or whose measured outcome is
`INSUFFICIENT_DATA`, is recorded with `included=False` and an explicit
`exclusion_reason` -- never silently dropped from the dataset table.
"""
from __future__ import annotations

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import (
    DiscoveryRecord,
    DiscoverySegment,
    HistoricalLearningRecord,
    MarketRegime,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
)
from .outcome_measurement import OUTCOME_INSUFFICIENT_DATA, get_outcome_measurement

DATASET_CONSTRUCTION_VERSION = "HOL-001"

REASON_NOT_YET_COMPLETED = "NOT_YET_COMPLETED"
REASON_OUTCOME_NOT_YET_MEASURED = "OUTCOME_NOT_YET_MEASURED"
REASON_INSUFFICIENT_DATA_OUTCOME = "INSUFFICIENT_DATA_OUTCOME"


class HistoricalLearningRecordImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "dataset_version",
    "prediction_id",
    "information_cutoff",
    "predicted_probability",
    "opportunity_score",
    "sma20_distance",
    "volume_ratio_20d",
    "atr_percent",
    "horizon_days",
    "market_regime",
    "sector",
    "market_cap_bucket",
    "discovery_source",
    "outcome_classification",
    "realized_return",
    "included",
    "exclusion_reason",
    "created_at",
)


@event.listens_for(HistoricalLearningRecord, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise HistoricalLearningRecordImmutableError(
            f"historical learning record {target.id} field(s) {changed} cannot be modified after creation"
        )


def build_learning_record(
    session: Session, prediction: Prediction, *, dataset_version: str = DATASET_CONSTRUCTION_VERSION
) -> HistoricalLearningRecord:
    """Build (or return the existing) learning record for one prediction
    under `dataset_version`. Idempotent by `(dataset_version, prediction_id)`
    uniqueness -- a dataset version, once constructed for a prediction, is
    immutable and never re-derived (AC: "dataset versions are immutable").
    Building a *new* dataset version (a different construction rule) is a
    distinct, separate set of rows, never a mutation of a prior version's."""
    existing = session.scalar(
        select(HistoricalLearningRecord).where(
            HistoricalLearningRecord.dataset_version == dataset_version,
            HistoricalLearningRecord.prediction_id == prediction.id,
        )
    )
    if existing is not None:
        return existing

    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id))
    included = False
    exclusion_reason = None
    outcome_classification = None
    realized_return = None

    if outcome is None:
        exclusion_reason = REASON_NOT_YET_COMPLETED
    else:
        measurement = get_outcome_measurement(session, outcome.id)
        if measurement is None:
            exclusion_reason = REASON_OUTCOME_NOT_YET_MEASURED
        elif measurement.outcome_classification == OUTCOME_INSUFFICIENT_DATA:
            exclusion_reason = REASON_INSUFFICIENT_DATA_OUTCOME
            outcome_classification = measurement.outcome_classification
        else:
            included = True
            outcome_classification = measurement.outcome_classification
            realized_return = measurement.realized_return

    generation = session.scalar(
        select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction.id)
    )
    scan_candidate = (
        session.get(ScanCandidate, generation.scan_candidate_id) if generation is not None else None
    )

    market_regime = None
    sector = None
    market_cap_bucket = None
    discovery_source = None
    if generation is not None:
        discovery = session.scalar(
            select(DiscoveryRecord)
            .where(DiscoveryRecord.recommendation_generation_id == generation.id)
            .order_by(DiscoveryRecord.id.asc())
        )
        if discovery is not None:
            discovery_source = discovery.source
            segment = session.scalar(
                select(DiscoverySegment).where(DiscoverySegment.discovery_record_id == discovery.id)
            )
            if segment is not None:
                sector = segment.sector
                market_cap_bucket = segment.market_cap_bucket
        if scan_candidate is not None:
            regime = session.scalar(select(MarketRegime).where(MarketRegime.scan_id == scan_candidate.scan_id))
            if regime is not None:
                market_regime = regime.regime

    record = HistoricalLearningRecord(
        dataset_version=dataset_version,
        prediction_id=prediction.id,
        information_cutoff=prediction.as_of_timestamp,
        predicted_probability=prediction.predicted_probability,
        opportunity_score=prediction.opportunity_score,
        sma20_distance=scan_candidate.sma20_distance if scan_candidate is not None else None,
        volume_ratio_20d=scan_candidate.volume_ratio_20d if scan_candidate is not None else None,
        atr_percent=scan_candidate.atr_percent if scan_candidate is not None else None,
        horizon_days=prediction.horizon_days,
        market_regime=market_regime,
        sector=sector,
        market_cap_bucket=market_cap_bucket,
        discovery_source=discovery_source,
        outcome_classification=outcome_classification,
        realized_return=realized_return,
        included=included,
        exclusion_reason=exclusion_reason,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def build_learning_dataset(
    session: Session, *, dataset_version: str = DATASET_CONSTRUCTION_VERSION
) -> tuple[HistoricalLearningRecord, ...]:
    """Build (or retrieve) learning records for every `Prediction` in the
    system under `dataset_version` -- reproducible (AC): the same predictions
    and outcomes always yield the same set of rows for a given version."""
    predictions = session.scalars(select(Prediction).order_by(Prediction.id.asc())).all()
    return tuple(build_learning_record(session, p, dataset_version=dataset_version) for p in predictions)


def get_learning_dataset(session: Session, dataset_version: str) -> tuple[HistoricalLearningRecord, ...]:
    return tuple(
        session.scalars(
            select(HistoricalLearningRecord)
            .where(HistoricalLearningRecord.dataset_version == dataset_version)
            .order_by(HistoricalLearningRecord.prediction_id.asc())
        ).all()
    )

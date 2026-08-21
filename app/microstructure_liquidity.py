"""EPIC-M1.128: incorporate liquidity, tradability, spread, volume,
price-band and gap behavior into opportunity quality and realistic
outcome evaluation.

Reuses rather than reinvents: `discovery_segmentation.classify_liquidity_
bucket` (the same `volume_ratio_20d` thresholds M1.34's own segmentation
and M1.98's execution-cost model already use) is the one liquidity-bucket
classifier in this platform -- this module never redefines it, only adds
the microstructure evidence M1.34/M1.98 didn't capture: turnover, gap
behavior, a liquidity-regime-change signal, and a circuit-band proxy.

**Spread is an honest, named gap, same posture as M1.98's own docstring**:
this platform ingests no real bid-ask spread or order-book depth from any
provider. Nothing here fabricates one -- `average_daily_turnover` (price
x volume) is the one real liquidity-depth proxy this platform's OHLCV
data can honestly support.

**Circuit-band detection is a documented proxy, not a confirmed exchange
freeze** -- M1.98's own docstring named this an out-of-scope gap because
this platform ingests no real circuit-band schedule (NSE bands vary
2%-20% per security and this platform has no per-stock band table).
`probable_circuit_band_event` flags a single-day move at or beyond
`PROBABLE_CIRCUIT_MOVE_THRESHOLD` -- consistent with having hit *some*
band, never claimed as proof a freeze actually occurred.

**Point-in-time safety** (AC: "historical microstructure features are
point-in-time safe"): `record_microstructure_snapshot` freezes every
value at `recorded_at` -- turnover only looks at bars strictly before it,
the gap is computed from the two most recent bars at or before it, and
the liquidity-regime comparison uses only `ScanCandidate` rows created at
or before it. The snapshot is immutable once recorded, exactly like every
other assessment/decision table in this platform.

**Execution-cost consumption** (AC: "execution-cost estimates can consume
microstructure evidence"): `get_microstructure_snapshot` is the read path
a future revision of M1.98's `execution_cost_model` could call to refine
its liquidity-surcharge decision with turnover/gap/circuit evidence
instead of `volume_ratio_20d` alone -- this module does not modify M1.98
itself, the same propose-only posture every gate/decision module in this
platform already holds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .discovery_segmentation import BUCKET_UNCLASSIFIED, classify_liquidity_bucket
from .models import (
    MarketPrice,
    MicrostructureSnapshot,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
)
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MICROSTRUCTURE_VERSION = "MSL-001"

DEFAULT_TURNOVER_LOOKBACK_DAYS = 20

GAP_BUCKET_LARGE = "LARGE_GAP"
GAP_BUCKET_MODERATE = "MODERATE_GAP"
GAP_BUCKET_SMALL = "SMALL_GAP"

# Fixed, documented, versioned policy thresholds (see module docstring) --
# not fitted or learned. Evaluated highest-first, first-match-wins.
GAP_BUCKET_THRESHOLDS = (
    (Decimal("0.05"), GAP_BUCKET_LARGE),
    (Decimal("0.02"), GAP_BUCKET_MODERATE),
    (Decimal("0"), GAP_BUCKET_SMALL),
)

# A single-day move at or beyond this magnitude is consistent with having
# hit *some* NSE circuit band (bands range 2%-20% per security; this
# platform has no per-stock band schedule) -- a documented proxy, not a
# confirmed freeze. See module docstring.
PROBABLE_CIRCUIT_MOVE_THRESHOLD = Decimal("0.10")

DIMENSION_LIQUIDITY_BUCKET = "liquidity_bucket"
DIMENSION_GAP_BUCKET = "gap_bucket"
DIMENSION_CIRCUIT_EVENT = "probable_circuit_band_event"

VERDICT_OK = "OK"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

IMMUTABLE_FIELDS = (
    "prediction_id", "liquidity_bucket", "previous_liquidity_bucket", "liquidity_regime_changed",
    "average_daily_turnover", "gap_percent", "gap_bucket", "probable_circuit_band_event",
    "recorded_at", "snapshot_version", "created_at",
)


class MicrostructureSnapshotImmutableError(RuntimeError):
    pass


@event.listens_for(MicrostructureSnapshot, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in IMMUTABLE_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise MicrostructureSnapshotImmutableError(
            f"microstructure snapshot {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class GapObservation:
    gap_percent: Decimal | None
    gap_bucket: str
    probable_circuit_band_event: bool


@dataclass(frozen=True)
class LiquidityRegimeAssessment:
    liquidity_bucket: str
    previous_liquidity_bucket: str | None
    regime_changed: bool


def classify_gap_bucket(gap_percent: Decimal | None) -> str:
    if gap_percent is None:
        return BUCKET_UNCLASSIFIED
    magnitude = abs(gap_percent)
    for threshold, bucket in GAP_BUCKET_THRESHOLDS:
        if magnitude >= threshold:
            return bucket
    return BUCKET_UNCLASSIFIED


def _linked_scan_candidate(session: Session, prediction_id: int) -> ScanCandidate | None:
    generation = session.scalar(
        select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction_id)
    )
    if generation is None:
        return None
    return session.get(ScanCandidate, generation.scan_candidate_id)


def compute_average_daily_turnover(
    session: Session, stock_id: int, *, as_of: datetime, lookback_days: int = DEFAULT_TURNOVER_LOOKBACK_DAYS
) -> Decimal | None:
    """Average `close * volume` over the `lookback_days` trading bars
    strictly before `as_of` -- the one liquidity-depth proxy this
    platform's OHLCV data can honestly support (no real spread/order-book
    depth is ingested; see module docstring)."""
    bars = session.scalars(
        select(MarketPrice)
        .where(MarketPrice.stock_id == stock_id, MarketPrice.timestamp < as_of)
        .order_by(MarketPrice.timestamp.desc())
        .limit(lookback_days)
    ).all()
    if not bars:
        return None
    turnovers = [bar.close * Decimal(bar.volume) for bar in bars]
    return sum(turnovers, Decimal("0")) / Decimal(len(turnovers))


def compute_gap_observation(session: Session, stock_id: int, *, as_of: datetime) -> GapObservation:
    """Uses only the two most recent bars at or before `as_of` (point-in-
    time safe: never looks past `as_of`). `gap_percent` is the latest
    bar's open vs. the prior bar's close; `probable_circuit_band_event`
    is evaluated on the latest bar's own close-vs-prior-close move, which
    can flag a large intraday move even without a large opening gap."""
    bars = session.scalars(
        select(MarketPrice)
        .where(MarketPrice.stock_id == stock_id, MarketPrice.timestamp <= as_of)
        .order_by(MarketPrice.timestamp.desc())
        .limit(2)
    ).all()
    if len(bars) < 2:
        return GapObservation(gap_percent=None, gap_bucket=BUCKET_UNCLASSIFIED, probable_circuit_band_event=False)

    latest, prior = bars[0], bars[1]
    if prior.close == 0:
        return GapObservation(gap_percent=None, gap_bucket=BUCKET_UNCLASSIFIED, probable_circuit_band_event=False)

    gap_percent = (latest.open - prior.close) / prior.close
    day_move_percent = (latest.close - prior.close) / prior.close
    return GapObservation(
        gap_percent=gap_percent,
        gap_bucket=classify_gap_bucket(gap_percent),
        probable_circuit_band_event=abs(day_move_percent) >= PROBABLE_CIRCUIT_MOVE_THRESHOLD,
    )


def assess_liquidity_regime(session: Session, stock_id: int, *, as_of: datetime) -> LiquidityRegimeAssessment:
    """Compares the most recent `ScanCandidate.volume_ratio_20d`-derived
    liquidity bucket at or before `as_of` against the one immediately
    before it (scope: "measure unusual volume and liquidity regime
    changes"). `previous_liquidity_bucket` is `None` (no comparison
    possible, not a claimed non-change) when fewer than two candidates
    exist for this stock as of `as_of`."""
    candidates = session.scalars(
        select(ScanCandidate)
        .where(ScanCandidate.stock_id == stock_id, ScanCandidate.created_at <= as_of)
        .order_by(ScanCandidate.created_at.desc())
        .limit(2)
    ).all()

    current_bucket = classify_liquidity_bucket(candidates[0].volume_ratio_20d) if candidates else BUCKET_UNCLASSIFIED
    previous_bucket = classify_liquidity_bucket(candidates[1].volume_ratio_20d) if len(candidates) > 1 else None
    regime_changed = previous_bucket is not None and previous_bucket != current_bucket

    return LiquidityRegimeAssessment(
        liquidity_bucket=current_bucket, previous_liquidity_bucket=previous_bucket, regime_changed=regime_changed
    )


def record_microstructure_snapshot(
    session: Session, prediction: Prediction, *, recorded_at: datetime
) -> MicrostructureSnapshot:
    """Idempotent by `prediction_id`. Every value is derived only from
    data available at or before `recorded_at` (AC: "historical
    microstructure features are point-in-time safe")."""
    existing = session.scalar(
        select(MicrostructureSnapshot).where(MicrostructureSnapshot.prediction_id == prediction.id)
    )
    if existing is not None:
        return existing

    regime = assess_liquidity_regime(session, prediction.stock_id, as_of=recorded_at)
    gap = compute_gap_observation(session, prediction.stock_id, as_of=recorded_at)
    turnover = compute_average_daily_turnover(session, prediction.stock_id, as_of=recorded_at)

    snapshot = MicrostructureSnapshot(
        prediction_id=prediction.id,
        liquidity_bucket=regime.liquidity_bucket,
        previous_liquidity_bucket=regime.previous_liquidity_bucket,
        liquidity_regime_changed=regime.regime_changed,
        average_daily_turnover=turnover,
        gap_percent=gap.gap_percent,
        gap_bucket=gap.gap_bucket,
        probable_circuit_band_event=gap.probable_circuit_band_event,
        recorded_at=recorded_at,
        snapshot_version=MICROSTRUCTURE_VERSION,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_microstructure_snapshot(session: Session, prediction_id: int) -> MicrostructureSnapshot | None:
    return session.scalar(select(MicrostructureSnapshot).where(MicrostructureSnapshot.prediction_id == prediction_id))


@dataclass(frozen=True)
class LiquiditySegmentMetric:
    dimension: str
    key: str
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None
    average_actual_return: Decimal | None
    verdict: str


@dataclass(frozen=True)
class LiquiditySegmentPerformanceReport:
    report_version: str
    evaluated_count: int
    metrics: tuple[LiquiditySegmentMetric, ...]


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def compute_liquidity_segment_performance(session: Session) -> LiquiditySegmentPerformanceReport:
    """Segments already-evaluated (`SUCCESS`/`FAILURE`) outcomes by this
    module's own `MicrostructureSnapshot` (liquidity bucket, gap bucket,
    circuit-event flag) -- a superset of M1.27's `DiscoverySegment`-based
    liquidity dimension, since it also carries the gap/circuit dimensions
    M1.27 structurally cannot (AC: "prediction performance can be
    compared across liquidity segments")."""
    rows = session.execute(
        select(Prediction, PredictionOutcome, MicrostructureSnapshot)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .join(MicrostructureSnapshot, MicrostructureSnapshot.prediction_id == Prediction.id)
        .where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    ).all()
    if not rows:
        return LiquiditySegmentPerformanceReport(report_version=MICROSTRUCTURE_VERSION, evaluated_count=0, metrics=())

    buckets: dict[tuple[str, str], list[PredictionOutcome]] = {}
    for _prediction, outcome, snapshot in rows:
        for dimension, key in (
            (DIMENSION_LIQUIDITY_BUCKET, snapshot.liquidity_bucket),
            (DIMENSION_GAP_BUCKET, snapshot.gap_bucket),
            (DIMENSION_CIRCUIT_EVENT, str(snapshot.probable_circuit_band_event)),
        ):
            buckets.setdefault((dimension, key), []).append(outcome)

    metrics = []
    for (dimension, key), outcomes in sorted(buckets.items()):
        success_count = sum(1 for o in outcomes if o.outcome == "SUCCESS")
        verdict = VERDICT_INSUFFICIENT_SAMPLE if len(outcomes) < MIN_SAMPLE_SIZE_FOR_COMPARISON else VERDICT_OK
        metrics.append(
            LiquiditySegmentMetric(
                dimension=dimension,
                key=key,
                evaluated_count=len(outcomes),
                success_count=success_count,
                success_rate=Decimal(success_count) / Decimal(len(outcomes)) if outcomes else None,
                average_actual_return=_mean([o.actual_return for o in outcomes]),
                verdict=verdict,
            )
        )

    return LiquiditySegmentPerformanceReport(
        report_version=MICROSTRUCTURE_VERSION, evaluated_count=len(rows), metrics=tuple(metrics)
    )

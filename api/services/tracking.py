"""Query service backing GET /api/v1/tracking/* (EPIC-M1.147).

Composes existing, already-merged domain modules -- nothing recomputed:
  - M1.5 ``PredictionOutcome`` for hit/stop/expiry rates and realized
    returns.
  - M1.77 ``PredictionTrustScore`` (latest by id, same convention as
    M1.135) for trust.
  - M1.23 ``ConfidenceCalibrationRecord.calibration_error`` for
    ``calibrationScore`` (average error magnitude; lower is better --
    this is a real, already-computed signal, not a new statistic
    invented here).
  - M1.34's ``classify_market_cap_bucket`` for the ``marketCap``
    breakdown dimension.

M1.119 (real-time outcome monitor) and M1.122 (statistical reliability/
uncertainty) are still APPROVED but not implemented (see EPIC-M1.147's
Dependencies note). M1.129 (benchmark-relative alpha) landed after this
EPIC's Dependencies note was written -- ``benchmarkReturn``/
``relativeReturn`` are now the average BROAD_MARKET-level benchmark
return / alpha across this window's closed, genuine predictions that
already have an
``app.benchmark_relative_alpha.BenchmarkRelativeAssessment`` row
(``None`` if none do yet -- this module never computes the assessment on
the fly, same read-only posture as the rest of this file). Consequences,
named rather than hidden:
  - The ``setup`` breakdown dimension always returns a single
    ``UNCLASSIFIED`` bucket -- no strategy/pattern-type classification
    module exists yet.
  - All rates/scores here are point-in-time averages, not confidence
    intervals or statistically-tested reliability claims (M1.122).

Only genuine, platform-produced predictions are counted -- every query
here requires a real ``RecommendationGeneration`` link (the same
provenance-link pattern M1.97/M1.98 established), so a revised
prediction's *original* is what's counted, matching how M1.135/137
identify recommendations.

EPIC-M3.15 adds the ``from``/``to``/``horizon``/``sector``/``marketCap``/
``regime``/``symbol``/``setup`` filter surface its own API Contract names
-- genuinely new (EPIC-M3.7 explicitly deferred "multi-dimension
simultaneous filtering" as a named follow-up gap). All four endpoints
accept the same optional [TrackingFilters]; ``summary``/``timeseries``
still require a resolved time window (either ``range`` or an explicit
``from``/``to`` pair), while ``breakdown``/``predictions`` keep their
pre-existing "whole history unless windowed" default when no ``from``/
``to`` is given, so passing no filters at all reproduces the exact
pre-M3.15 query and result set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.benchmark_relative_alpha import LEVEL_BROAD_MARKET
from app.discovery_segmentation import BUCKET_UNCLASSIFIED, classify_market_cap_bucket
from app.models import (
    BenchmarkRelativeAssessment,
    ConfidenceCalibrationRecord,
    MarketRegime,
    Prediction,
    PredictionOutcome,
    PredictionTrustScore,
    RecommendationGeneration,
    ScanCandidate,
    Stock,
)

from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

from ..errors import ValidationError
from ..pagination import DEFAULT_PAGE_SIZE
from .keyset import decode_cursor, encode_cursor, keyset_predicate
from ..schemas.tracking import (
    BreakdownItem,
    BreakdownResponse,
    MODEL_VERSION_MIXED,
    TimeseriesPoint,
    TimeseriesResponse,
    TrackedPrediction,
    TrackingSummary,
    VALID_BREAKDOWN_DIMENSIONS,
    VALID_BUCKETS,
    VALID_PREDICTION_STATUSES,
    VALID_TIMESERIES_METRICS,
)

RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
MIN_HORIZON_DAYS = 1
MAX_HORIZON_DAYS = 7  # product constraint: 1-7 trading-day horizon only


@dataclass(frozen=True)
class TrackingFilters:
    """EPIC-M3.15 — optional narrowing filters shared by all four
    `/tracking/*` (and `/performance/*`) endpoints. Every field defaults to
    `None` (no filter), so `TrackingFilters()` reproduces the exact
    pre-M3.15 unfiltered result set."""

    horizon: int | None = None
    sector: str | None = None
    market_cap: str | None = None
    regime: str | None = None
    symbol: str | None = None
    setup: str | None = None

    def is_empty(self) -> bool:
        return not any(
            [self.horizon, self.sector, self.market_cap, self.regime, self.symbol, self.setup]
        )


def make_filters(
    *,
    horizon: int | None = None,
    sector: str | None = None,
    market_cap: str | None = None,
    regime: str | None = None,
    symbol: str | None = None,
    setup: str | None = None,
) -> TrackingFilters:
    if horizon is not None and not (MIN_HORIZON_DAYS <= horizon <= MAX_HORIZON_DAYS):
        raise ValidationError(
            f"horizon must be between {MIN_HORIZON_DAYS} and {MAX_HORIZON_DAYS}, got {horizon!r}",
            field_errors={"horizon": f"must be between {MIN_HORIZON_DAYS} and {MAX_HORIZON_DAYS}"},
        )
    return TrackingFilters(horizon=horizon, sector=sector, market_cap=market_cap, regime=regime, symbol=symbol, setup=setup)


def _validate_range(range_key: str) -> int:
    if range_key not in RANGE_DAYS:
        raise ValidationError(f"range must be one of {tuple(RANGE_DAYS)}, got {range_key!r}", field_errors={"range": f"must be one of {tuple(RANGE_DAYS)}"})
    return RANGE_DAYS[range_key]


def _resolve_window(
    range_key: str | None, from_: datetime | None, to_: datetime | None
) -> tuple[datetime, datetime]:
    """EPIC-M3.15: an explicit `from`/`to` pair overrides `range` when
    given. Both must be supplied together -- a single-sided bound is
    ambiguous (open-ended windows aren't part of this contract)."""
    if from_ is not None or to_ is not None:
        if from_ is None or to_ is None:
            raise ValidationError("from and to must be provided together", field_errors={"from": "required when to is set", "to": "required when from is set"})
        since = _as_aware_utc(from_)
        until = _as_aware_utc(to_)
        if since >= until:
            raise ValidationError("from must be before to", field_errors={"from": "must be before to"})
        return since, until
    days = _validate_range(range_key or "30d")
    now = datetime.now(timezone.utc)
    return now - timedelta(days=days), now


def _as_aware_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on DateTime(timezone=True) round-trip; normalize
    # before any Python-side arithmetic (SQL-level comparisons against a
    # bound aware datetime are unaffected and already work elsewhere).
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _avg(values: list[Decimal]) -> Decimal | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def _latest_trust_scores(session: Session, prediction_ids: list[int]) -> list[Decimal]:
    if not prediction_ids:
        return []
    latest_ids = (
        select(func.max(PredictionTrustScore.id))
        .where(PredictionTrustScore.prediction_id.in_(prediction_ids))
        .group_by(PredictionTrustScore.prediction_id)
    )
    return [
        v for v in session.execute(
            select(PredictionTrustScore.overall_trust_score).where(PredictionTrustScore.id.in_(latest_ids))
        ).scalars().all()
        if v is not None
    ]


def _outcomes_for(session: Session, prediction_ids: list[int]) -> list[PredictionOutcome]:
    if not prediction_ids:
        return []
    return list(session.scalars(select(PredictionOutcome).where(PredictionOutcome.prediction_id.in_(prediction_ids))).all())


def _latest_broad_market_assessments(session: Session, prediction_ids: list[int]) -> list[BenchmarkRelativeAssessment]:
    if not prediction_ids:
        return []
    latest_ids = (
        select(func.max(BenchmarkRelativeAssessment.id))
        .where(
            BenchmarkRelativeAssessment.prediction_id.in_(prediction_ids),
            BenchmarkRelativeAssessment.benchmark_level == LEVEL_BROAD_MARKET,
        )
        .group_by(BenchmarkRelativeAssessment.prediction_id)
    )
    return list(session.scalars(select(BenchmarkRelativeAssessment).where(BenchmarkRelativeAssessment.id.in_(latest_ids))).all())


def _calibration_errors_for(session: Session, prediction_ids: list[int]) -> list[Decimal]:
    if not prediction_ids:
        return []
    return [
        v for v in session.execute(
            select(ConfidenceCalibrationRecord.calibration_error).where(
                ConfidenceCalibrationRecord.prediction_id.in_(prediction_ids),
                ConfidenceCalibrationRecord.calibration_error.is_not(None),
            )
        ).scalars().all()
        if v is not None
    ]


def _filtered_rows(
    session: Session,
    filters: TrackingFilters,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list:
    """EPIC-M3.15: (Prediction, Stock, scan_candidate_id) rows for every
    genuine prediction (real `RecommendationGeneration` link -- the
    provenance-link pattern M1.97/98 established), narrowed by whatever
    SQL-expressible filters are given. `marketCap`/`regime`/`setup` aren't
    plain columns, so they're applied afterwards by `_apply_python_filters`
    against these same rows -- same two-pass approach `get_breakdown`
    already used pre-M3.15 for `marketCap`/`regime`."""
    stmt = (
        select(Prediction, Stock, RecommendationGeneration.scan_candidate_id)
        .join(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .join(Stock, Stock.id == Prediction.stock_id)
    )
    if since is not None:
        stmt = stmt.where(Prediction.as_of_timestamp >= since, Prediction.as_of_timestamp < until)
    if filters.horizon is not None:
        stmt = stmt.where(Prediction.horizon_days == filters.horizon)
    if filters.sector is not None:
        stmt = stmt.where(Stock.sector == filters.sector)
    if filters.symbol is not None:
        stmt = stmt.where(Stock.symbol == filters.symbol)
    return session.execute(stmt).all()


def _regime_lookup(session: Session, rows: list) -> tuple[dict[int, int], dict[int, str]]:
    candidate_ids = [scan_candidate_id for _p, _s, scan_candidate_id in rows if scan_candidate_id is not None]
    scan_ids_by_candidate: dict[int, int] = {}
    if candidate_ids:
        scan_ids_by_candidate = dict(
            session.execute(select(ScanCandidate.id, ScanCandidate.scan_id).where(ScanCandidate.id.in_(candidate_ids))).all()
        )
    regime_by_scan: dict[int, str] = {}
    scan_ids = list(set(scan_ids_by_candidate.values()))
    if scan_ids:
        regime_by_scan = dict(
            session.execute(select(MarketRegime.scan_id, MarketRegime.regime).where(MarketRegime.scan_id.in_(scan_ids))).all()
        )
    return scan_ids_by_candidate, regime_by_scan


def _apply_python_filters(
    rows: list,
    filters: TrackingFilters,
    scan_ids_by_candidate: dict[int, int],
    regime_by_scan: dict[int, str],
) -> list:
    if filters.market_cap is None and filters.regime is None and filters.setup is None:
        return rows
    out = []
    for prediction, stock, scan_candidate_id in rows:
        if filters.market_cap is not None and classify_market_cap_bucket(stock.market_cap) != filters.market_cap:
            continue
        if filters.regime is not None:
            scan_id = scan_ids_by_candidate.get(scan_candidate_id) if scan_candidate_id is not None else None
            regime_key = regime_by_scan.get(scan_id, "UNKNOWN") if scan_id is not None else "UNKNOWN"
            if regime_key != filters.regime:
                continue
        if filters.setup is not None and filters.setup != BUCKET_UNCLASSIFIED:
            # No strategy/pattern-type classification module exists, so
            # every genuine prediction is honestly "UNCLASSIFIED" -- any
            # other requested `setup` value matches nothing.
            continue
        out.append((prediction, stock, scan_candidate_id))
    return out


def _filtered_prediction_ids(
    session: Session, since: datetime, until: datetime, filters: TrackingFilters
) -> list[int]:
    rows = _filtered_rows(session, filters, since, until)
    scan_ids_by_candidate, regime_by_scan = (
        _regime_lookup(session, rows) if filters.regime is not None else ({}, {})
    )
    matched = _apply_python_filters(rows, filters, scan_ids_by_candidate, regime_by_scan)
    return [prediction.id for prediction, _stock, _scan_candidate_id in matched]


def get_summary(
    session: Session,
    range_key: str,
    *,
    from_: datetime | None = None,
    to_: datetime | None = None,
    filters: TrackingFilters | None = None,
) -> TrackingSummary:
    filters = filters or TrackingFilters()
    since, until = _resolve_window(range_key, from_, to_)
    window = until - since
    prev_since = since - window

    prediction_ids = _filtered_prediction_ids(session, since, until, filters)
    predictions = (
        list(session.scalars(select(Prediction).where(Prediction.id.in_(prediction_ids))).all())
        if prediction_ids else []
    )

    outcomes = _outcomes_for(session, prediction_ids)
    closed_count = len(outcomes)
    target_hit_rate = Decimal(sum(1 for o in outcomes if o.target_hit)) / Decimal(closed_count) if closed_count else None
    stop_loss_rate = Decimal(sum(1 for o in outcomes if o.stop_hit)) / Decimal(closed_count) if closed_count else None
    expired = sum(1 for o in outcomes if o.outcome != "UNEVALUABLE" and not o.target_hit and not o.stop_hit)
    horizon_expiry_rate = Decimal(expired) / Decimal(closed_count) if closed_count else None
    avg_realized_return = _avg([o.actual_return for o in outcomes])

    closed_prediction_ids = {o.prediction_id for o in outcomes}
    avg_predicted_return = _avg([p.target_return for p in predictions if p.id in closed_prediction_ids])

    broad_market_assessments = _latest_broad_market_assessments(session, list(closed_prediction_ids))
    benchmark_return = _avg([a.benchmark_return_pct for a in broad_market_assessments])
    relative_return = _avg([a.relative_alpha for a in broad_market_assessments])

    calibration_score = _avg(_calibration_errors_for(session, prediction_ids))

    trust_score = _avg(_latest_trust_scores(session, prediction_ids))
    prev_prediction_ids = _filtered_prediction_ids(session, prev_since, since, filters)
    prev_trust_score = _avg(_latest_trust_scores(session, prev_prediction_ids))
    trust_delta = (trust_score - prev_trust_score) if (trust_score is not None and prev_trust_score is not None) else None

    model_versions = {p.model_version for p in predictions}
    if not model_versions:
        model_version = None
    elif len(model_versions) == 1:
        model_version = next(iter(model_versions))
    else:
        model_version = MODEL_VERSION_MIXED

    # EPIC-M3.15: an explicit from/to window has no single named "range" --
    # reported honestly as "custom" rather than echoing back a `range_key`
    # that wasn't actually what determined the window.
    reported_range = range_key if (from_ is None and to_ is None) else "custom"

    return TrackingSummary(
        range=reported_range,
        predictionCount=len(prediction_ids),
        closedCount=closed_count,
        targetHitRate=target_hit_rate,
        stopLossRate=stop_loss_rate,
        horizonExpiryRate=horizon_expiry_rate,
        avgRealizedReturn=avg_realized_return,
        avgPredictedReturn=avg_predicted_return,
        calibrationScore=calibration_score,
        trustScore=trust_score,
        trustDelta=trust_delta,
        modelVersion=model_version,
        benchmarkReturn=benchmark_return,
        relativeReturn=relative_return,
        smallSample=closed_count < MIN_SAMPLE_SIZE_FOR_COMPARISON,
    )


def get_timeseries(
    session: Session,
    metric: str,
    range_key: str,
    bucket: str,
    *,
    from_: datetime | None = None,
    to_: datetime | None = None,
    filters: TrackingFilters | None = None,
) -> TimeseriesResponse:
    filters = filters or TrackingFilters()
    if metric not in VALID_TIMESERIES_METRICS:
        raise ValidationError(f"metric must be one of {VALID_TIMESERIES_METRICS}", field_errors={"metric": f"must be one of {VALID_TIMESERIES_METRICS}"})
    if bucket not in VALID_BUCKETS:
        raise ValidationError(f"bucket must be one of {VALID_BUCKETS}", field_errors={"bucket": f"must be one of {VALID_BUCKETS}"})
    since, until = _resolve_window(range_key, from_, to_)

    prediction_ids = _filtered_prediction_ids(session, since, until, filters)
    predictions = (
        list(session.scalars(select(Prediction).where(Prediction.id.in_(prediction_ids))).all())
        if prediction_ids else []
    )

    bucket_delta = timedelta(days=1) if bucket == "day" else timedelta(weeks=1)
    groups: dict[datetime, list[Prediction]] = {}
    for p in predictions:
        elapsed = _as_aware_utc(p.as_of_timestamp) - since
        bucket_index = int(elapsed / bucket_delta)
        start = since + bucket_index * bucket_delta
        groups.setdefault(start, []).append(p)

    points: list[TimeseriesPoint] = []
    for start in sorted(groups):
        bucket_prediction_ids = [p.id for p in groups[start]]
        if metric == "trust":
            values = _latest_trust_scores(session, bucket_prediction_ids)
        elif metric == "hitRate":
            outcomes = _outcomes_for(session, bucket_prediction_ids)
            values = [Decimal(1) if o.target_hit else Decimal(0) for o in outcomes]
        elif metric == "return":
            values = [o.actual_return for o in _outcomes_for(session, bucket_prediction_ids)]
        else:  # calibration
            values = _calibration_errors_for(session, bucket_prediction_ids)
        points.append(TimeseriesPoint(bucketStart=start, value=_avg(values), sampleCount=len(values)))

    reported_range = range_key if (from_ is None and to_ is None) else "custom"
    return TimeseriesResponse(metric=metric, range=reported_range, bucket=bucket, points=points)


def get_breakdown(
    session: Session,
    dimension: str,
    *,
    from_: datetime | None = None,
    to_: datetime | None = None,
    filters: TrackingFilters | None = None,
) -> BreakdownResponse:
    filters = filters or TrackingFilters()
    if dimension not in VALID_BREAKDOWN_DIMENSIONS:
        raise ValidationError(f"dimension must be one of {VALID_BREAKDOWN_DIMENSIONS}", field_errors={"dimension": f"must be one of {VALID_BREAKDOWN_DIMENSIONS}"})

    # EPIC-M3.15: no time window by default (unchanged pre-M3.15 behavior --
    # whole immutable history), unless an explicit from/to is given.
    since = until = None
    if from_ is not None or to_ is not None:
        since, until = _resolve_window(None, from_, to_)

    rows = _filtered_rows(session, filters, since, until)
    scan_ids_by_candidate, regime_by_scan = (
        _regime_lookup(session, rows) if (dimension == "regime" or filters.regime is not None) else ({}, {})
    )
    rows = _apply_python_filters(rows, filters, scan_ids_by_candidate, regime_by_scan)

    if dimension == "setup":
        # No strategy/pattern-type classification module exists yet --
        # an honest single bucket rather than a fabricated taxonomy. No
        # bucket at all (empty items) when filters leave nothing to
        # report, matching every other dimension's empty-result shape.
        all_ids = [prediction.id for prediction, _stock, _scid in rows]
        if not all_ids:
            return BreakdownResponse(dimension=dimension, items=[])
        outcomes = _outcomes_for(session, all_ids)
        item = BreakdownItem(
            key=BUCKET_UNCLASSIFIED,
            predictionCount=len(all_ids),
            closedCount=len(outcomes),
            targetHitRate=(Decimal(sum(1 for o in outcomes if o.target_hit)) / Decimal(len(outcomes))) if outcomes else None,
            avgRealizedReturn=_avg([o.actual_return for o in outcomes]),
            smallSample=len(outcomes) < MIN_SAMPLE_SIZE_FOR_COMPARISON,
        )
        return BreakdownResponse(dimension=dimension, items=[item])

    buckets: dict[str, list[Prediction]] = {}
    for prediction, stock, scan_candidate_id in rows:
        if dimension == "horizon":
            key = f"{prediction.horizon_days}d"
        elif dimension == "sector":
            key = stock.sector or "UNKNOWN"
        elif dimension == "marketCap":
            key = classify_market_cap_bucket(stock.market_cap)
        elif dimension == "stock":  # EPIC-M3.7: per-stock breakdown
            key = stock.symbol
        else:  # regime
            scan_id = scan_ids_by_candidate.get(scan_candidate_id)
            key = regime_by_scan.get(scan_id, "UNKNOWN") if scan_id else "UNKNOWN"
        buckets.setdefault(key, []).append(prediction)

    items = []
    for key, predictions in sorted(buckets.items()):
        prediction_ids = [p.id for p in predictions]
        outcomes = _outcomes_for(session, prediction_ids)
        items.append(
            BreakdownItem(
                key=key,
                predictionCount=len(predictions),
                closedCount=len(outcomes),
                targetHitRate=(Decimal(sum(1 for o in outcomes if o.target_hit)) / Decimal(len(outcomes))) if outcomes else None,
                avgRealizedReturn=_avg([o.actual_return for o in outcomes]),
                smallSample=len(outcomes) < MIN_SAMPLE_SIZE_FOR_COMPARISON,
            )
        )
    return BreakdownResponse(dimension=dimension, items=items)


@dataclass
class TrackedPredictionsPage:
    items: list[TrackedPrediction]
    next_cursor: str | None


def list_tracked_predictions(
    session: Session,
    status: str,
    *,
    cursor: str | None,
    page_size: int = DEFAULT_PAGE_SIZE,
    from_: datetime | None = None,
    to_: datetime | None = None,
    filters: TrackingFilters | None = None,
) -> TrackedPredictionsPage:
    filters = filters or TrackingFilters()
    if status not in VALID_PREDICTION_STATUSES:
        raise ValidationError(f"status must be one of {VALID_PREDICTION_STATUSES}", field_errors={"status": f"must be one of {VALID_PREDICTION_STATUSES}"})

    since = until = None
    if from_ is not None or to_ is not None:
        since, until = _resolve_window(None, from_, to_)

    # EPIC-M3.15: `marketCap`/`regime`/`setup` aren't plain columns, so
    # constrain the paginated query with an `IN` clause over a
    # pre-computed eligible-id set rather than post-filtering fetched
    # pages -- post-filtering after `LIMIT` would silently under-fill or
    # break keyset pagination's "every item exactly once" guarantee.
    eligible_ids: set[int] | None = None
    if since is not None or not filters.is_empty():
        rows = _filtered_rows(session, filters, since, until)
        scan_ids_by_candidate, regime_by_scan = (
            _regime_lookup(session, rows) if filters.regime is not None else ({}, {})
        )
        matched = _apply_python_filters(rows, filters, scan_ids_by_candidate, regime_by_scan)
        eligible_ids = {prediction.id for prediction, _stock, _scid in matched}
        if not eligible_ids:
            return TrackedPredictionsPage(items=[], next_cursor=None)

    stmt = (
        select(Prediction, Stock.symbol, RecommendationGeneration.id, PredictionOutcome)
        .join(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
    )
    if status == "closed":
        stmt = stmt.where(PredictionOutcome.id.is_not(None))
    else:
        stmt = stmt.where(PredictionOutcome.id.is_(None))
    if eligible_ids is not None:
        stmt = stmt.where(Prediction.id.in_(eligible_ids))

    sort_expr = Prediction.as_of_timestamp
    id_col = RecommendationGeneration.id
    if cursor:
        cursor_value, cursor_id = decode_cursor(cursor, is_datetime=True)
        if cursor_value is not None:
            stmt = stmt.where(keyset_predicate(sort_expr, id_col, cursor_value, cursor_id, descending=True))

    stmt = stmt.order_by(sort_expr.desc(), id_col.desc()).limit(page_size + 1)
    rows = session.execute(stmt).all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]

    items = [
        TrackedPrediction(
            id=generation_id,
            symbol=symbol,
            status="closed" if outcome is not None else "active",
            asOf=prediction.as_of_timestamp,
            horizonDays=prediction.horizon_days,
            predictedReturn=prediction.target_return,
            realizedReturn=outcome.actual_return if outcome is not None else None,
            outcome=outcome.outcome if outcome is not None else None,
            modelVersion=prediction.model_version,
        )
        for prediction, symbol, generation_id, outcome in rows
    ]

    next_cursor = None
    if has_more and rows:
        last_prediction, _symbol, last_generation_id, _outcome = rows[-1]
        next_cursor = encode_cursor(last_prediction.as_of_timestamp, last_generation_id)

    return TrackedPredictionsPage(items=items, next_cursor=next_cursor)

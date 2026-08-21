"""EPIC-M1.104: calibrate prediction probabilities (and, through that,
Trust Score) at stock, setup, sector, market-cap and horizon segments
instead of relying only on M1.11's global calibration -- while never
producing a falsely precise number from a segment too sparse to trust.

Reuses this platform's already-established segmentation vocabulary
rather than inventing a second one: `SEGMENT_SECTOR`/`SEGMENT_MARKET_CAP`/
`SEGMENT_HORIZON` and `discovery_segmentation.classify_market_cap_bucket`
are M1.82's own; the SMA20-distance/volume-ratio bucket thresholds used
to define `SEGMENT_SETUP` are M1.85's own (`SMA20_DISTANCE_THRESHOLDS`/
`VOLUME_RATIO_THRESHOLDS`). Only `SEGMENT_STOCK` and the setup-bucket
combination itself are new to this EPIC. Calibration error and its
`OVERCONFIDENT`/`UNDERCONFIDENT`/`WELL_CALIBRATED`/`INSUFFICIENT_SAMPLE`
vocabulary and `MATERIAL_ERROR_THRESHOLD` are M1.11's own
(`app.calibration`), reused unchanged.

**Hierarchical fallback** (scope): for one prediction, `FALLBACK_ORDER`
walks from the most specific segment (its own stock) to the broadest
(global), stopping at the first level whose sample size for that exact
segment key reaches `MIN_SAMPLE_SIZE` (M1.11's own floor) -- never
computing an error from fewer samples than that, at any level, "so
sparse segments" cannot "produce falsely precise probabilities" (scope).
The full chain considered (not just the resolved level) is persisted in
`fallback_chain` for auditability.

Propose-only: no write path to `Prediction`, `PredictionTrustScore`, or
`TrustControlDecision` -- "feed validated calibration into Trust Score"
(scope) remains a future revision's job, the same posture M1.101/
M1.102/M1.103's own signals already established.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calibration import INSUFFICIENT_SAMPLE, MATERIAL_ERROR_THRESHOLD, MIN_SAMPLE_SIZE, OVERCONFIDENT, UNDERCONFIDENT, WELL_CALIBRATED
from .discovery_segmentation import classify_market_cap_bucket
from .models import Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate, SegmentCalibrationAssessment, Stock
from .prediction_attribution import SMA20_DISTANCE_FALLBACK, SMA20_DISTANCE_THRESHOLDS, VOLUME_RATIO_FALLBACK, VOLUME_RATIO_THRESHOLDS
from .prediction_quality_benchmark import SEGMENT_HORIZON, SEGMENT_MARKET_CAP, SEGMENT_SECTOR

SEGMENT_CALIBRATION_VERSION = "SGC-001"

SEGMENT_STOCK = "STOCK"
SEGMENT_SETUP = "SETUP"
SEGMENT_GLOBAL = "GLOBAL"
GLOBAL_KEY = "ALL"

# Fixed, documented order: most specific segment first, global last.
FALLBACK_ORDER = (SEGMENT_STOCK, SEGMENT_SETUP, SEGMENT_SECTOR, SEGMENT_MARKET_CAP, SEGMENT_HORIZON, SEGMENT_GLOBAL)


def _bucket(value: Decimal | None, thresholds: tuple, fallback: str) -> str | None:
    if value is None:
        return None
    for threshold, bucket in thresholds:
        if value >= threshold:
            return bucket
    return fallback


def _setup_key(sma20_distance: Decimal | None, volume_ratio_20d: Decimal | None) -> str | None:
    sma_bucket = _bucket(sma20_distance, SMA20_DISTANCE_THRESHOLDS, SMA20_DISTANCE_FALLBACK)
    volume_bucket = _bucket(volume_ratio_20d, VOLUME_RATIO_THRESHOLDS, VOLUME_RATIO_FALLBACK)
    if sma_bucket is None or volume_bucket is None:
        return None
    return f"{sma_bucket}_{volume_bucket}"


def _segment_keys(prediction: Prediction, stock: Stock, sma20_distance: Decimal | None, volume_ratio_20d: Decimal | None) -> dict[str, str | None]:
    return {
        SEGMENT_STOCK: str(prediction.stock_id),
        SEGMENT_SETUP: _setup_key(sma20_distance, volume_ratio_20d),
        SEGMENT_SECTOR: stock.sector,
        SEGMENT_MARKET_CAP: classify_market_cap_bucket(stock.market_cap),
        SEGMENT_HORIZON: str(prediction.horizon_days),
        SEGMENT_GLOBAL: GLOBAL_KEY,
    }


def _evaluated_rows_for_model(session: Session, model_version: str) -> list[tuple[Prediction, PredictionOutcome, Stock, Decimal | None, Decimal | None]]:
    rows = session.execute(
        select(Prediction, PredictionOutcome, Stock, ScanCandidate.sma20_distance, ScanCandidate.volume_ratio_20d)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .outerjoin(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .outerjoin(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .where(Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    ).all()
    return list(rows)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def assess_segment_calibration(
    session: Session, prediction: Prediction, *, model_version: str | None = None, evaluated_at: datetime
) -> SegmentCalibrationAssessment:
    """Idempotent by `(prediction_id, evaluated_at)`."""
    existing = session.scalar(
        select(SegmentCalibrationAssessment).where(
            SegmentCalibrationAssessment.prediction_id == prediction.id,
            SegmentCalibrationAssessment.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    resolved_model_version = model_version or prediction.model_version
    rows = _evaluated_rows_for_model(session, resolved_model_version)

    stock = session.get(Stock, prediction.stock_id)
    generation = session.scalar(select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction.id))
    candidate = session.get(ScanCandidate, generation.scan_candidate_id) if generation is not None else None
    target_keys = _segment_keys(
        prediction, stock,
        candidate.sma20_distance if candidate is not None else None,
        candidate.volume_ratio_20d if candidate is not None else None,
    )

    row_keys = [(_segment_keys(p, s, sma, vol), p, o) for p, o, s, sma, vol in rows]

    fallback_chain: list[dict] = []
    resolved_level = None
    resolved_key = None
    resolved_subset: list[tuple[Prediction, PredictionOutcome]] = []

    for level in FALLBACK_ORDER:
        key = target_keys[level]
        if key is None:
            fallback_chain.append({"level": level, "key": None, "sample_count": 0, "skipped": True})
            continue
        subset = [(p, o) for keys, p, o in row_keys if keys[level] == key]
        fallback_chain.append({"level": level, "key": key, "sample_count": len(subset), "skipped": False})
        if len(subset) >= MIN_SAMPLE_SIZE and resolved_level is None:
            resolved_level = level
            resolved_key = key
            resolved_subset = subset

    if resolved_level is None:
        # Not even GLOBAL cleared the sample floor -- report GLOBAL as the
        # resolved level (the broadest possible) with an honest
        # INSUFFICIENT_SAMPLE verdict rather than fabricating a number.
        resolved_level = SEGMENT_GLOBAL
        resolved_key = target_keys[SEGMENT_GLOBAL]
        resolved_subset = [(p, o) for keys, p, o in row_keys if keys[SEGMENT_GLOBAL] == resolved_key]

    sample_count = len(resolved_subset)

    if sample_count < MIN_SAMPLE_SIZE:
        predicted_mean = None
        observed_rate = None
        calibration_error = None
        verdict = INSUFFICIENT_SAMPLE
    else:
        predicted_mean = _mean([p.predicted_probability for p, _o in resolved_subset])
        success_count = sum(1 for _p, o in resolved_subset if o.outcome == "SUCCESS")
        observed_rate = Decimal(success_count) / Decimal(sample_count)
        calibration_error = observed_rate - predicted_mean
        if calibration_error >= MATERIAL_ERROR_THRESHOLD:
            verdict = UNDERCONFIDENT
        elif calibration_error <= -MATERIAL_ERROR_THRESHOLD:
            verdict = OVERCONFIDENT
        else:
            verdict = WELL_CALIBRATED

    assessment = SegmentCalibrationAssessment(
        prediction_id=prediction.id, model_version=resolved_model_version, resolved_segment_level=resolved_level,
        resolved_segment_key=resolved_key, resolved_sample_count=sample_count, predicted_mean=predicted_mean,
        observed_rate=observed_rate, calibration_error=calibration_error, verdict=verdict,
        fallback_chain=fallback_chain, evaluated_at=evaluated_at, calibration_rule_version=SEGMENT_CALIBRATION_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_segment_calibration_history(session: Session, prediction_id: int) -> tuple[SegmentCalibrationAssessment, ...]:
    return tuple(
        session.scalars(
            select(SegmentCalibrationAssessment)
            .where(SegmentCalibrationAssessment.prediction_id == prediction_id)
            .order_by(SegmentCalibrationAssessment.id.asc())
        ).all()
    )

"""EPIC-M1.113: decide, per specialization dimension and segment,
whether a candidate ("specialized") model version demonstrably
outperforms the current global production model on that specific
segment -- horizon, regime, sector, or setup -- before recommending
that predictions for that segment be routed to it.

This platform has no live multi-model serving infrastructure (M1.83's
own docstring already establishes: "this platform's production
pipeline runs exactly one model version at a time"). `routing_verdict`
is therefore an honest, propose-only recommendation -- no write path to
`Prediction`, `ModelPromotion`, or any production table -- for a future
deployment step to act on, the same posture this platform's whole
family of propose/gate signals already established.

**Define specialization dimensions**: reuses the exact same four
already-established dimension names this platform's segmentation
EPICs use -- `HORIZON` (M1.79/M1.104), `REGIME` (M1.79), `SECTOR`
(M1.82/M1.104/M1.109), `SETUP` (M1.104/M1.108) -- and reads segment
membership directly off M1.85's already-immutable, already-bucketed
`PredictionAttributionSnapshot` columns wherever possible (`horizon_days`,
`regime`, `sma20_distance_bucket`+`volume_ratio_bucket`), joining to
`Stock.sector` only for the one dimension the snapshot doesn't carry.

**Compare specialized versus global models / route only when sufficient
evidence exists / maintain global fallback for sparse segments**:
reuses M1.100's own "require independent confirmation across two
disjoint windows" pattern -- a candidate is `ROUTE_TO_SPECIALIZED` only
if the specialized model's segment success rate exceeds the global
model's *in both* a baseline and a later, disjoint confirmation window;
otherwise `USE_GLOBAL_FALLBACK` (including every insufficient-sample
case), never fabricating a specialization decision from one window's
noise.

**Prevent fragmentation and overfitting**: the caller supplies
`candidate_count` -- how many specialization candidates are being
evaluated together in this batch -- and `adjusted_margin = WEAKNESS_
MARGIN * candidate_count` (the same fixed Bonferroni-style scaling
M1.100/M1.108 already established for their own, different multiplicity
questions), so testing many segments/models at once requires a
proportionally larger edge before any one of them is routed.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionAttributionSnapshot, SpecializationRoutingDecision, Stock
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

SPECIALIZATION_ROUTING_VERSION = "MSR-001"

DIMENSION_HORIZON = "HORIZON"
DIMENSION_REGIME = "REGIME"
DIMENSION_SECTOR = "SECTOR"
DIMENSION_SETUP = "SETUP"

VERDICT_ROUTE_TO_SPECIALIZED = "ROUTE_TO_SPECIALIZED"
VERDICT_USE_GLOBAL_FALLBACK = "USE_GLOBAL_FALLBACK"

SEGMENT_VERDICT_VALIDATED = "VALIDATED"
SEGMENT_VERDICT_NOT_VALIDATED = "NOT_VALIDATED"
SEGMENT_VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


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


def _segment_outcomes(session: Session, *, model_version: str, dimension: str, segment_key: str, window: EvaluationWindow) -> list[str]:
    query = select(PredictionAttributionSnapshot.outcome, PredictionAttributionSnapshot.prediction_id).where(
        PredictionAttributionSnapshot.model_version == model_version
    )
    if window.start is not None:
        query = query.where(PredictionAttributionSnapshot.snapshotted_at >= window.start)
    if window.end is not None:
        query = query.where(PredictionAttributionSnapshot.snapshotted_at <= window.end)

    if dimension == DIMENSION_HORIZON:
        query = query.where(PredictionAttributionSnapshot.horizon_days == int(segment_key))
        rows = session.execute(query).all()
        return [outcome for outcome, _pid in rows]

    if dimension == DIMENSION_REGIME:
        query = query.where(PredictionAttributionSnapshot.regime == segment_key)
        rows = session.execute(query).all()
        return [outcome for outcome, _pid in rows]

    if dimension == DIMENSION_SETUP:
        sma_bucket, _sep, volume_bucket = segment_key.partition("_")
        query = query.where(
            PredictionAttributionSnapshot.sma20_distance_bucket == sma_bucket,
            PredictionAttributionSnapshot.volume_ratio_bucket == volume_bucket,
        )
        rows = session.execute(query).all()
        return [outcome for outcome, _pid in rows]

    if dimension == DIMENSION_SECTOR:
        query = query.select_from(PredictionAttributionSnapshot).join(
            Prediction, Prediction.id == PredictionAttributionSnapshot.prediction_id
        ).join(Stock, Stock.id == Prediction.stock_id).where(Stock.sector == segment_key)
        rows = session.execute(query).all()
        return [outcome for outcome, _pid in rows]

    raise ValueError(f"unknown specialization dimension '{dimension}'")


def _segment_verdict(specialized_rate: Decimal | None, specialized_count: int, global_rate: Decimal | None, global_count: int, adjusted_margin: Decimal) -> str:
    if specialized_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or global_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or specialized_rate is None or global_rate is None:
        return SEGMENT_VERDICT_INSUFFICIENT_SAMPLE
    delta = specialized_rate - global_rate
    return SEGMENT_VERDICT_VALIDATED if delta >= adjusted_margin else SEGMENT_VERDICT_NOT_VALIDATED


def evaluate_specialization_candidate(
    session: Session,
    *,
    dimension: str,
    segment_key: str,
    specialized_model_version: str,
    global_model_version: str,
    baseline_window: EvaluationWindow,
    confirmation_window: EvaluationWindow,
    candidate_count: int,
    computed_at: datetime,
) -> SpecializationRoutingDecision:
    """Idempotent by `(dimension, segment_key, specialized_model_version,
    global_model_version, computed_at)`. Raises nothing on overlapping
    windows here (unlike M1.100) since baseline/confirmation compare two
    *different models* on the same segment, not the same model's own
    history -- but the two windows must still be disjoint from each
    other for a genuine independent-replication check."""
    existing = session.scalar(
        select(SpecializationRoutingDecision).where(
            SpecializationRoutingDecision.dimension == dimension, SpecializationRoutingDecision.segment_key == segment_key,
            SpecializationRoutingDecision.specialized_model_version == specialized_model_version,
            SpecializationRoutingDecision.global_model_version == global_model_version,
            SpecializationRoutingDecision.computed_at == computed_at,
        )
    )
    if existing is not None:
        return existing

    adjusted_margin = WEAKNESS_MARGIN * Decimal(max(1, candidate_count))

    def _windowed_verdict(window: EvaluationWindow) -> tuple[str, int, int]:
        specialized_outcomes = _segment_outcomes(session, model_version=specialized_model_version, dimension=dimension, segment_key=segment_key, window=window)
        global_outcomes = _segment_outcomes(session, model_version=global_model_version, dimension=dimension, segment_key=segment_key, window=window)
        specialized_count = len(specialized_outcomes)
        global_count = len(global_outcomes)
        specialized_rate = _rate(sum(1 for o in specialized_outcomes if o == "SUCCESS"), specialized_count)
        global_rate = _rate(sum(1 for o in global_outcomes if o == "SUCCESS"), global_count)
        verdict = _segment_verdict(specialized_rate, specialized_count, global_rate, global_count, adjusted_margin)
        return verdict, specialized_count, global_count

    baseline_verdict, baseline_specialized_count, baseline_global_count = _windowed_verdict(baseline_window)
    confirmation_verdict, confirmation_specialized_count, confirmation_global_count = _windowed_verdict(confirmation_window)

    routing_verdict = (
        VERDICT_ROUTE_TO_SPECIALIZED
        if baseline_verdict == SEGMENT_VERDICT_VALIDATED and confirmation_verdict == SEGMENT_VERDICT_VALIDATED
        else VERDICT_USE_GLOBAL_FALLBACK
    )

    decision = SpecializationRoutingDecision(
        dimension=dimension, segment_key=segment_key, specialized_model_version=specialized_model_version,
        global_model_version=global_model_version, candidate_count=max(1, candidate_count), adjusted_margin=adjusted_margin,
        baseline_window_label=baseline_window.label, confirmation_window_label=confirmation_window.label,
        baseline_verdict=baseline_verdict, confirmation_verdict=confirmation_verdict,
        specialized_sample_count=confirmation_specialized_count, global_sample_count=confirmation_global_count,
        routing_verdict=routing_verdict, computed_at=computed_at, routing_rule_version=SPECIALIZATION_ROUTING_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_specialization_routing_history(session: Session, *, dimension: str, segment_key: str) -> tuple[SpecializationRoutingDecision, ...]:
    return tuple(
        session.scalars(
            select(SpecializationRoutingDecision)
            .where(SpecializationRoutingDecision.dimension == dimension, SpecializationRoutingDecision.segment_key == segment_key)
            .order_by(SpecializationRoutingDecision.id.asc())
        ).all()
    )

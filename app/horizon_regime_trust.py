"""EPIC-M1.79: measure prediction trust separately by forecast horizon
and market regime, so a weak segment can never hide behind a healthy
aggregate.

A genuinely different lens than M1.77's `PredictionTrustScore`, not a
duplicate: M1.77 blends horizon reliability (M1.75) and regime
reliability (M1.41) into ONE composite number per prediction; this
module keeps them -- and their combination -- as separate, independently
queryable segments (AC: "a prediction can show different trust for
different horizons"). Both read the same underlying evaluated-prediction
history; neither recomputes the other.

"Combine horizon and regime evidence when sample sizes permit" (scope):
`segment_type` is `HORIZON`, `REGIME`, or `COMBINED` depending on which
of `horizon_days`/`regime` the caller supplies -- `COMBINED` requires
both and is gated by the exact same minimum-sample floor as the other
two, never computed from a smaller, less-reliable slice just because it
looks more specific.

"Preserve sample size and uncertainty" (scope): every segment persists
its own `sample_count` and a standard binomial standard error
(`sqrt(p*(1-p)/n)`) alongside `success_rate` -- a real, simple, well-known
uncertainty measure, not a fabricated confidence claim.

"Feed trust into positive-only recommendation gating" (scope) is a
forward-compatible capability, not an enforcement this module performs
itself: `is_low_trust` is exposed for a future gate (e.g. M1.81) to
consume -- this module has no write path to `Prediction`/`ScanCandidate`/
any selection table, matching this platform's established propose/gate
split (M1.65, M1.74, M1.77).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .market_regime import classify_market_regime
from .models import HorizonRegimeTrust, Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

HORIZON_REGIME_TRUST_VERSION = "HRT-001"

SEGMENT_HORIZON = "HORIZON"
SEGMENT_REGIME = "REGIME"
SEGMENT_COMBINED = "COMBINED"

VERDICT_SUFFICIENT = "SUFFICIENT"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

# Fixed, documented, versioned policy constant: a segment succeeding
# less than half the time, with enough sample to trust the number, is
# definitionally low-trust.
LOW_TRUST_THRESHOLD = Decimal("0.5")


class MissingSegmentDimensionError(ValueError):
    """Raised when neither `horizon_days` nor `regime` is provided --
    at least one dimension is required to define a segment."""


class HorizonRegimeTrustImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "model_version",
    "segment_type",
    "horizon_days",
    "regime",
    "sample_count",
    "success_rate",
    "success_rate_standard_error",
    "verdict",
    "is_low_trust",
    "computed_at",
    "trust_rule_version",
    "created_at",
)


@event.listens_for(HorizonRegimeTrust, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise HorizonRegimeTrustImmutableError(
            f"horizon/regime trust {target.id} field(s) {changed} cannot be modified after creation"
        )


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _standard_error(success_rate: Decimal, sample_count: int) -> Decimal:
    variance = float(success_rate) * (1 - float(success_rate)) / sample_count
    return Decimal(str(variance ** 0.5))


def _regime_for_prediction(session: Session, prediction: Prediction) -> str:
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one()
    return classify_market_regime(session, scan_id).regime


def _evaluated_rows(
    session: Session, *, model_version: str, horizon_days: int | None, regime: str | None
) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if horizon_days is not None:
        query = query.where(Prediction.horizon_days == horizon_days)
    rows = list(session.execute(query).all())
    if regime is None:
        return rows
    return [(p, o) for p, o in rows if _regime_for_prediction(session, p) == regime]


def compute_horizon_regime_trust(
    session: Session,
    *,
    model_version: str,
    horizon_days: int | None = None,
    regime: str | None = None,
    computed_at: datetime,
) -> HorizonRegimeTrust:
    """Computes one segment's trust -- `HORIZON` if only `horizon_days`
    is given, `REGIME` if only `regime` is given, `COMBINED` if both are
    given. Never silently overfits a sparse segment: below
    `MIN_SAMPLE_SIZE_FOR_COMPARISON`, the verdict is explicitly
    `VERDICT_INSUFFICIENT_SAMPLE` and `success_rate`/`success_rate_
    standard_error` stay `None` (AC: "insufficient samples are
    explicit"; "sparse segments are marked insufficient rather than
    overfit")."""
    if horizon_days is None and regime is None:
        raise MissingSegmentDimensionError("at least one of horizon_days or regime must be provided")
    segment_type = (
        SEGMENT_COMBINED if horizon_days is not None and regime is not None
        else SEGMENT_HORIZON if horizon_days is not None
        else SEGMENT_REGIME
    )

    rows = _evaluated_rows(session, model_version=model_version, horizon_days=horizon_days, regime=regime)
    sample_count = len(rows)

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        success_rate = None
        standard_error = None
        is_low_trust = False
    else:
        verdict = VERDICT_SUFFICIENT
        success_count = sum(1 for _, o in rows if o.outcome == "SUCCESS")
        success_rate = _rate(success_count, sample_count)
        standard_error = _standard_error(success_rate, sample_count)
        is_low_trust = success_rate < LOW_TRUST_THRESHOLD

    trust = HorizonRegimeTrust(
        model_version=model_version,
        segment_type=segment_type,
        horizon_days=horizon_days,
        regime=regime,
        sample_count=sample_count,
        success_rate=success_rate,
        success_rate_standard_error=standard_error,
        verdict=verdict,
        is_low_trust=is_low_trust,
        computed_at=computed_at,
        trust_rule_version=HORIZON_REGIME_TRUST_VERSION,
    )
    session.add(trust)
    session.commit()
    session.refresh(trust)
    return trust


def get_trust_history(
    session: Session, *, model_version: str, segment_type: str, horizon_days: int | None = None, regime: str | None = None
) -> tuple[HorizonRegimeTrust, ...]:
    query = select(HorizonRegimeTrust).where(
        HorizonRegimeTrust.model_version == model_version, HorizonRegimeTrust.segment_type == segment_type
    )
    if horizon_days is not None:
        query = query.where(HorizonRegimeTrust.horizon_days == horizon_days)
    if regime is not None:
        query = query.where(HorizonRegimeTrust.regime == regime)
    return tuple(session.scalars(query.order_by(HorizonRegimeTrust.id.asc())).all())


def get_latest_trust(
    session: Session, *, model_version: str, segment_type: str, horizon_days: int | None = None, regime: str | None = None
) -> HorizonRegimeTrust | None:
    history = get_trust_history(
        session, model_version=model_version, segment_type=segment_type, horizon_days=horizon_days, regime=regime
    )
    return history[-1] if history else None

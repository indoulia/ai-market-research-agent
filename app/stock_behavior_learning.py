"""EPIC-M1.107: learn prediction reliability and recurring response
characteristics at the individual security level -- by horizon and
regime -- without letting sparse stock history create false confidence.

Hierarchical fallback (scope) walks from the most specific segment to
the broadest, the same pattern M1.104 already established for
calibration: `STOCK_HORIZON_REGIME -> STOCK_HORIZON -> STOCK_ONLY ->
GLOBAL_HORIZON_REGIME -> GLOBAL`. `GLOBAL_HORIZON_REGIME` is a pure
read of M1.79's already-computed `HorizonRegimeTrust` (`COMBINED`
segment) -- never recomputed here -- so this module's own new
contribution is exactly the three STOCK-scoped levels above it in the
chain.

"Keep personal preferences separate from global stock behavior" (scope)
holds structurally, not by convention: this module has no import from
`app.user_preferences`, `app.feedback_learning_signals`, or
`app.recommendation_feedback` at all -- there is no code path here that
could let a user's subjective preference signal leak into an otherwise
objective, evidence-based stock-behavior measurement.

Propose-only: no write path to `Prediction`, `PredictionTrustScore`, or
any ranking table -- "feed stock-specific evidence into Trust Score and
ranking" (scope) remains a future revision's job, the same posture
M1.101-M1.106 already established.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .horizon_regime_trust import SEGMENT_COMBINED, get_latest_trust
from .market_regime import classify_market_regime
from .models import Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate, StockBehaviorAssessment
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

STOCK_BEHAVIOR_VERSION = "SBL-001"

LEVEL_STOCK_HORIZON_REGIME = "STOCK_HORIZON_REGIME"
LEVEL_STOCK_HORIZON = "STOCK_HORIZON"
LEVEL_STOCK_ONLY = "STOCK_ONLY"
LEVEL_GLOBAL_HORIZON_REGIME = "GLOBAL_HORIZON_REGIME"
LEVEL_GLOBAL = "GLOBAL"

VERDICT_MEASURED = "MEASURED"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _regime_for_prediction(session: Session, prediction: Prediction) -> str | None:
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one_or_none()
    if scan_id is None:
        return None
    return classify_market_regime(session, scan_id).regime


def _evaluated_outcomes(
    session: Session, *, model_version: str, stock_id: int | None, horizon_days: int | None, regime: str | None
) -> list[str]:
    rows = session.execute(
        select(Prediction, PredictionOutcome.outcome)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    ).all()

    outcomes = []
    for prediction, outcome in rows:
        if stock_id is not None and prediction.stock_id != stock_id:
            continue
        if horizon_days is not None and prediction.horizon_days != horizon_days:
            continue
        if regime is not None and _regime_for_prediction(session, prediction) != regime:
            continue
        outcomes.append(outcome)
    return outcomes


def assess_stock_behavior(
    session: Session, *, stock_id: int, model_version: str, horizon_days: int, regime: str | None, evaluated_at: datetime
) -> StockBehaviorAssessment:
    """Idempotent by `(stock_id, model_version, horizon_days, regime,
    evaluated_at)`."""
    existing = session.scalar(
        select(StockBehaviorAssessment).where(
            StockBehaviorAssessment.stock_id == stock_id, StockBehaviorAssessment.model_version == model_version,
            StockBehaviorAssessment.horizon_days == horizon_days, StockBehaviorAssessment.regime == regime,
            StockBehaviorAssessment.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    fallback_chain: list[dict] = []
    resolved_level = None
    resolved_sample_count = 0
    resolved_success_rate: Decimal | None = None

    if regime is not None:
        outcomes = _evaluated_outcomes(session, model_version=model_version, stock_id=stock_id, horizon_days=horizon_days, regime=regime)
        fallback_chain.append({"level": LEVEL_STOCK_HORIZON_REGIME, "sample_count": len(outcomes)})
        if len(outcomes) >= MIN_SAMPLE_SIZE_FOR_COMPARISON:
            resolved_level, resolved_sample_count = LEVEL_STOCK_HORIZON_REGIME, len(outcomes)
            resolved_success_rate = _rate(sum(1 for o in outcomes if o == "SUCCESS"), len(outcomes))

    if resolved_level is None:
        outcomes = _evaluated_outcomes(session, model_version=model_version, stock_id=stock_id, horizon_days=horizon_days, regime=None)
        fallback_chain.append({"level": LEVEL_STOCK_HORIZON, "sample_count": len(outcomes)})
        if len(outcomes) >= MIN_SAMPLE_SIZE_FOR_COMPARISON:
            resolved_level, resolved_sample_count = LEVEL_STOCK_HORIZON, len(outcomes)
            resolved_success_rate = _rate(sum(1 for o in outcomes if o == "SUCCESS"), len(outcomes))

    if resolved_level is None:
        outcomes = _evaluated_outcomes(session, model_version=model_version, stock_id=stock_id, horizon_days=None, regime=None)
        fallback_chain.append({"level": LEVEL_STOCK_ONLY, "sample_count": len(outcomes)})
        if len(outcomes) >= MIN_SAMPLE_SIZE_FOR_COMPARISON:
            resolved_level, resolved_sample_count = LEVEL_STOCK_ONLY, len(outcomes)
            resolved_success_rate = _rate(sum(1 for o in outcomes if o == "SUCCESS"), len(outcomes))

    if resolved_level is None and regime is not None:
        global_segment = get_latest_trust(session, model_version=model_version, segment_type=SEGMENT_COMBINED, horizon_days=horizon_days, regime=regime)
        sample_count = global_segment.sample_count if global_segment is not None else 0
        fallback_chain.append({"level": LEVEL_GLOBAL_HORIZON_REGIME, "sample_count": sample_count})
        if global_segment is not None and sample_count >= MIN_SAMPLE_SIZE_FOR_COMPARISON:
            resolved_level, resolved_sample_count = LEVEL_GLOBAL_HORIZON_REGIME, sample_count
            resolved_success_rate = global_segment.success_rate

    if resolved_level is None:
        outcomes = _evaluated_outcomes(session, model_version=model_version, stock_id=None, horizon_days=None, regime=None)
        fallback_chain.append({"level": LEVEL_GLOBAL, "sample_count": len(outcomes)})
        resolved_level, resolved_sample_count = LEVEL_GLOBAL, len(outcomes)
        if len(outcomes) >= MIN_SAMPLE_SIZE_FOR_COMPARISON:
            resolved_success_rate = _rate(sum(1 for o in outcomes if o == "SUCCESS"), len(outcomes))

    verdict = VERDICT_MEASURED if resolved_sample_count >= MIN_SAMPLE_SIZE_FOR_COMPARISON else VERDICT_INSUFFICIENT_SAMPLE

    assessment = StockBehaviorAssessment(
        stock_id=stock_id, model_version=model_version, horizon_days=horizon_days, regime=regime,
        resolved_level=resolved_level, resolved_sample_count=resolved_sample_count,
        observed_success_rate=resolved_success_rate, verdict=verdict, fallback_chain=fallback_chain,
        evaluated_at=evaluated_at, behavior_rule_version=STOCK_BEHAVIOR_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_stock_behavior_history(session: Session, stock_id: int) -> tuple[StockBehaviorAssessment, ...]:
    return tuple(
        session.scalars(
            select(StockBehaviorAssessment).where(StockBehaviorAssessment.stock_id == stock_id).order_by(StockBehaviorAssessment.id.asc())
        ).all()
    )

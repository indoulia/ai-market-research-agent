from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import MarketPrice, Prediction, PredictionOutcome

# EPIC-M1.95: the versioned identity of the label-generation methodology
# below (same-day tie-break rule, horizon-expiry/invalidation
# classification) -- recorded on every outcome going forward so a future
# change to this methodology is never mistaken for a change to history.
# Pre-EPIC rows have `label_methodology_version IS NULL`, honestly
# meaning "not recorded at the time", never backfilled with a guess.
LABEL_METHODOLOGY_VERSION = "LBL-001"

# EPIC-M1.95's own canonical label-category vocabulary (scope: "define
# target-hit, stop-loss-hit, horizon-expiry and invalidation outcomes"),
# derived purely from an already-computed `PredictionOutcome` -- see
# `classify_label_category`.
LABEL_TARGET_HIT = "TARGET_HIT"
LABEL_STOP_LOSS_HIT = "STOP_LOSS_HIT"
LABEL_HORIZON_EXPIRY = "HORIZON_EXPIRY"
LABEL_INVALIDATED = "INVALIDATED"

# Outcomes are objective historical fact once computed; never rewrite them (mirrors the
# immutability guarantee app/recommendations.py enforces on the original recommendation).
IMMUTABLE_FIELDS = (
    "prediction_id",
    "evaluation_date",
    "highest_price",
    "lowest_price",
    "closing_price",
    "maximum_return",
    "maximum_drawdown",
    "actual_return",
    "prediction_error",
    "target_hit",
    "stop_hit",
    "outcome",
    "label_methodology_version",
)


class OutcomeImmutableError(RuntimeError):
    pass


class RecommendationNotCompletedError(RuntimeError):
    """Raised when fewer than horizon_days trading sessions have elapsed since the recommendation."""


class RecommendationAlreadyEvaluatedError(RuntimeError):
    pass


@event.listens_for(PredictionOutcome, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise OutcomeImmutableError(
            f"outcome for prediction {target.prediction_id} field(s) {changed} cannot be modified after creation"
        )


def _has_valid_ohlc(row: MarketPrice) -> bool:
    prices = (row.open, row.high, row.low, row.close)
    if any(price <= 0 for price in prices):
        return False
    if row.volume <= 0:
        return False
    if row.high < max(row.open, row.low, row.close):
        return False
    if row.low > min(row.open, row.high, row.close):
        return False
    return True


@dataclass(frozen=True)
class _ExitEvent:
    price: Decimal
    at: datetime
    target_hit: bool
    stop_hit: bool


def _find_exit(window: list[MarketPrice], entry_price: Decimal, target_return: Decimal, stop_return: Decimal) -> _ExitEvent:
    target_price = entry_price * (1 + target_return)
    stop_price = entry_price * (1 + stop_return)
    for row in window:
        # Stop-loss is checked before the profit target on the same trading day: daily OHLC
        # data can't tell us which was touched first intraday, and protecting capital first
        # is the conservative, documented convention this EPIC uses to stay deterministic.
        if row.low <= stop_price:
            return _ExitEvent(price=stop_price, at=row.timestamp, target_hit=False, stop_hit=True)
        if row.high >= target_price:
            return _ExitEvent(price=target_price, at=row.timestamp, target_hit=True, stop_hit=False)
    last = window[-1]
    return _ExitEvent(price=last.close, at=last.timestamp, target_hit=False, stop_hit=False)


def classify_label_category(outcome: PredictionOutcome) -> str:
    """The one canonical, deterministic mapping from an already-computed
    `PredictionOutcome` to this EPIC's four-category label vocabulary
    (scope: "labels support model training, calibration and trust
    measurement consistently") -- a pure function of fields `evaluate_
    recommendation` already wrote, never a new computation or a second
    opinion on what happened. `outcome.outcome == "UNEVALUABLE"` (bad
    OHLC data made the true exit undeterminable) is the one existing case
    where a label genuinely cannot be trusted, so it maps to
    `LABEL_INVALIDATED` -- never fabricated as a target/stop/expiry hit
    it never was."""
    if outcome.outcome == "UNEVALUABLE":
        return LABEL_INVALIDATED
    if outcome.target_hit:
        return LABEL_TARGET_HIT
    if outcome.stop_hit:
        return LABEL_STOP_LOSS_HIT
    return LABEL_HORIZON_EXPIRY


def evaluate_recommendation(session: Session, prediction: Prediction) -> PredictionOutcome | None:
    existing = session.execute(
        select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise RecommendationAlreadyEvaluatedError(f"prediction {prediction.id} already has an outcome")

    rows = (
        session.execute(
            select(MarketPrice)
            .where(
                MarketPrice.stock_id == prediction.stock_id,
                MarketPrice.timestamp > prediction.as_of_timestamp,
            )
            .order_by(MarketPrice.timestamp.asc())
        )
        .scalars()
        .all()
    )
    if len(rows) < prediction.horizon_days:
        return None

    window = list(rows[: prediction.horizon_days])
    highest_price = max(row.high for row in window)
    lowest_price = min(row.low for row in window)
    closing_price = window[-1].close
    maximum_return = (highest_price - prediction.entry_price) / prediction.entry_price
    maximum_drawdown = (lowest_price - prediction.entry_price) / prediction.entry_price

    if not all(_has_valid_ohlc(row) for row in window):
        outcome = PredictionOutcome(
            prediction_id=prediction.id,
            evaluation_date=window[-1].timestamp,
            highest_price=highest_price,
            lowest_price=lowest_price,
            closing_price=closing_price,
            maximum_return=maximum_return,
            maximum_drawdown=maximum_drawdown,
            actual_return=Decimal("0"),
            prediction_error=Decimal("0") - prediction.target_return,
            target_hit=False,
            stop_hit=False,
            outcome="UNEVALUABLE",
            label_methodology_version=LABEL_METHODOLOGY_VERSION,
        )
        session.add(outcome)
        session.flush()
        return outcome

    exit_event = _find_exit(window, prediction.entry_price, prediction.target_return, prediction.stop_return)
    actual_return = (exit_event.price - prediction.entry_price) / prediction.entry_price
    prediction_error = actual_return - prediction.target_return
    if exit_event.target_hit:
        result = "SUCCESS"
    elif exit_event.stop_hit:
        result = "FAILURE"
    else:
        result = "SUCCESS" if actual_return > 0 else "FAILURE"

    outcome = PredictionOutcome(
        prediction_id=prediction.id,
        evaluation_date=exit_event.at,
        highest_price=highest_price,
        lowest_price=lowest_price,
        closing_price=closing_price,
        maximum_return=maximum_return,
        maximum_drawdown=maximum_drawdown,
        actual_return=actual_return,
        prediction_error=prediction_error,
        target_hit=exit_event.target_hit,
        stop_hit=exit_event.stop_hit,
        outcome=result,
        label_methodology_version=LABEL_METHODOLOGY_VERSION,
    )
    session.add(outcome)
    prediction.status = "EVALUATED"
    session.flush()
    return outcome

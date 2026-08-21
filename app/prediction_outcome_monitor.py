"""EPIC-M1.119: continuously monitor active positive recommendations and
determine target hits, stop-loss hits, horizon expiry, material price
movements and assumption invalidation in a timely, auditable and
provider-independent manner -- independent of the end-of-day batch
evaluation `app.outcomes.evaluate_recommendation` (M1.5) already performs.

**Why a new module rather than extending `app.outcomes`**: M1.5's
`evaluate_recommendation` deliberately only fires once a *full*
`horizon_days`-length window of `MarketPrice` rows exists (`if len(rows) <
prediction.horizon_days: return None`) -- it is an end-of-horizon batch
evaluator, not a timely one. A target/stop-loss hit that occurs on day 1
of a 5-day horizon is invisible to it until day 5. This module evaluates
every new bar as soon as it arrives, so target/stop detection is
independent of end-of-day processing (AC) -- without ever touching or
duplicating M1.5's own immutable `PredictionOutcome` row for the same
prediction.

**Provider-independent, timely, auditable**: every event records the
exact detection timestamp (`detected_at`), the observed evidence
timestamp and price (`observed_at`/`observed_price`), the data provider
(`MarketPrice.source`, never hardcoded) and the prediction/methodology
version in force (`prediction_version`), per the EPIC's own acceptance
criteria.

**Absolute target/stop prices**: reuses M1.47's `RecommendationPublication`
(the platform's one canonical absolute target/stop-loss price per
prediction) when it exists; falls back to deriving the same prices
directly from `Prediction.entry_price/target_return/stop_return` for a
prediction that was never published under M1.47 (e.g. a rejected/
unpublished one still being monitored for research purposes). Either way
the derivation is identical arithmetic to M1.47's own, never a second,
divergent formula.

**Assumption invalidation**: reuses M1.112's `assess_assumption_decay`
read-only -- that module already computes `MATERIAL_DECAY` +
`invalidation_recommended` but explicitly has "no write path to
Prediction or any recommendation-facing table" (its own docstring). This
module is the first EPIC to act on that signal: a `MATERIAL_DECAY`
verdict with `invalidation_recommended=True` closes the prediction here
as `INVALIDATED`, evidenced by the exact `AssumptionDecayAssessment.id`
that triggered it.

**Immutability**: `PredictionOutcomeEvent` rows are strictly append-only
-- the `before_update` listener below rejects every field change
unconditionally, stronger than the partial-immutability pattern other
EPICs use, because this module never has a legitimate reason to revise
one of its own past observations. Closure is idempotent: once any
terminal event exists for a `prediction_id`, `evaluate_prediction_realtime`
returns it unchanged rather than re-evaluating (AC: "outcome closure is
idempotent").

**Stale/missing data**: a real gap between the newest available
`MarketPrice` bar and `as_of`, observed during a live trading session,
never silently leaves a prediction `ACTIVE` with no evidence trail (AC:
"stale/missing market data cannot silently close a prediction") -- it is
recorded as a non-terminal `DATA_UNRESOLVED` event instead, deduplicated
against the same gap so repeated polling does not spam duplicate rows.

**Feeding downstream systems**: `get_terminal_event`/`get_event_history`
are the read surface this module offers so usefulness, attribution,
Trust Score and learning systems (M1.119's own AC) can consume a closed
prediction's real-time outcome; wiring any specific consumer to call
them is left to that consumer's own EPIC, matching this platform's
established compositional-delta convention (e.g. M1.122/M1.129/M1.130).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .assumption_decay_tracker import VERDICT_MATERIAL_DECAY, assess_assumption_decay
from .models import MarketPrice, Prediction, PredictionOutcomeEvent
from .schedule_orchestration import is_trading_session
from .target_stop_loss import TARGET_STOP_METHODOLOGY_VERSION, get_publication

MONITOR_RULE_VERSION = "RTM-001"

STATE_ACTIVE = "ACTIVE"
STATE_TARGET_HIT = "TARGET_HIT"
STATE_STOP_LOSS_HIT = "STOP_LOSS_HIT"
STATE_HORIZON_EXPIRED = "HORIZON_EXPIRED"
STATE_INVALIDATED = "INVALIDATED"
STATE_DATA_UNRESOLVED = "DATA_UNRESOLVED"

TERMINAL_STATES = frozenset(
    {STATE_TARGET_HIT, STATE_STOP_LOSS_HIT, STATE_HORIZON_EXPIRED, STATE_INVALIDATED}
)

# Fixed, documented policy constant: a gap this large between the newest
# known price bar and `as_of`, observed during a live trading session,
# means price data is missing/stale rather than merely "not yet fetched
# today" -- not learned or fitted.
STALE_BAR_GAP_DAYS = 3

# Fixed, documented policy constant (scope: "detect material movements
# that should trigger re-analysis"): an unrealized move that has already
# covered this fraction of the distance to target or stop, without
# actually hitting either, is material enough to flag for re-analysis --
# a signal only, never a state transition of its own.
MATERIAL_MOVEMENT_RATIO_THRESHOLD = Decimal("0.6")


class PredictionOutcomeEventImmutableError(RuntimeError):
    pass


@event.listens_for(PredictionOutcomeEvent, "before_update")
def _reject_any_update(mapper, connection, target):
    state = inspect(target)
    changed = [
        attr.key
        for attr in state.mapper.column_attrs
        if state.attrs[attr.key].history.added or state.attrs[attr.key].history.deleted
    ]
    if changed:
        raise PredictionOutcomeEventImmutableError(
            f"prediction outcome event {target.id} is append-only; field(s) {changed} cannot be modified"
        )


def _valid_ohlc(row: MarketPrice) -> bool:
    prices = (row.open, row.high, row.low, row.close)
    if any(price <= 0 for price in prices):
        return False
    if row.high < max(row.open, row.low, row.close):
        return False
    if row.low > min(row.open, row.high, row.close):
        return False
    return True


def get_target_stop_prices(session: Session, prediction: Prediction) -> tuple[Decimal, Decimal, str]:
    """Absolute (target_price, stop_loss_price, prediction_version). Prefers
    M1.47's published, canonical absolute prices; falls back to deriving
    the identical arithmetic directly from the prediction's own frozen
    fields for a prediction that was never published."""
    publication = get_publication(session, prediction.id)
    if publication is not None and publication.published:
        version = f"{prediction.model_version}:{publication.methodology_version}"
        return publication.target_price, publication.stop_loss_price, version

    target_price = prediction.entry_price * (Decimal("1") + prediction.target_return)
    stop_loss_price = prediction.entry_price * (Decimal("1") + prediction.stop_return)
    version = f"{prediction.model_version}:{TARGET_STOP_METHODOLOGY_VERSION}-unpublished"
    return target_price, stop_loss_price, version


def get_event_history(session: Session, prediction_id: int) -> tuple[PredictionOutcomeEvent, ...]:
    return tuple(
        session.scalars(
            select(PredictionOutcomeEvent)
            .where(PredictionOutcomeEvent.prediction_id == prediction_id)
            .order_by(PredictionOutcomeEvent.id.asc())
        ).all()
    )


def get_terminal_event(session: Session, prediction_id: int) -> PredictionOutcomeEvent | None:
    return session.scalar(
        select(PredictionOutcomeEvent)
        .where(
            PredictionOutcomeEvent.prediction_id == prediction_id,
            PredictionOutcomeEvent.state.in_(tuple(TERMINAL_STATES)),
        )
        .order_by(PredictionOutcomeEvent.id.asc())
    )


def detect_material_movement(
    entry_price: Decimal, target_price: Decimal, stop_loss_price: Decimal, bar_close: Decimal
) -> bool:
    """Pure signal, not a state transition: True when the unrealized move
    from `entry_price` to `bar_close` already covers
    `MATERIAL_MOVEMENT_RATIO_THRESHOLD` of the distance to whichever of
    target/stop it is moving toward."""
    move = bar_close - entry_price
    if move > 0:
        distance = target_price - entry_price
    elif move < 0:
        distance = entry_price - stop_loss_price
    else:
        return False
    if distance <= 0:
        return False
    return abs(move) / distance >= MATERIAL_MOVEMENT_RATIO_THRESHOLD


@dataclass(frozen=True)
class _Evaluation:
    state: str
    observed_at: datetime | None
    observed_price: Decimal | None
    provider: str | None
    evidence: dict


def _evaluate_bars(
    rows: list[MarketPrice], *, entry_price: Decimal, target_price: Decimal, stop_loss_price: Decimal, horizon_days: int
) -> _Evaluation | None:
    valid = [row for row in rows if _valid_ohlc(row)]
    for row in valid:
        if row.low <= stop_loss_price:
            return _Evaluation(
                state=STATE_STOP_LOSS_HIT,
                observed_at=row.timestamp,
                observed_price=stop_loss_price,
                provider=row.source,
                evidence={"trigger": "stop_loss_price", "bar_low": str(row.low)},
            )
        if row.high >= target_price:
            return _Evaluation(
                state=STATE_TARGET_HIT,
                observed_at=row.timestamp,
                observed_price=target_price,
                provider=row.source,
                evidence={"trigger": "target_price", "bar_high": str(row.high)},
            )

    if len(valid) >= horizon_days:
        last = valid[-1]
        return _Evaluation(
            state=STATE_HORIZON_EXPIRED,
            observed_at=last.timestamp,
            observed_price=last.close,
            provider=last.source,
            evidence={"trigger": "horizon_expiry", "bars_observed": len(valid)},
        )

    return None


def evaluate_prediction_realtime(
    session: Session, prediction: Prediction, *, as_of: datetime, holiday_dates: frozenset[date] = frozenset()
) -> PredictionOutcomeEvent | None:
    """Idempotent and deterministic for the same `prediction` and set of
    already-persisted `MarketPrice` rows (AC). Returns the existing
    terminal event unchanged if the prediction is already closed; a newly
    recorded event (terminal, or non-terminal `DATA_UNRESOLVED`) if this
    call produces one; or `None` if the prediction remains `ACTIVE` with
    nothing new to record."""
    existing_terminal = get_terminal_event(session, prediction.id)
    if existing_terminal is not None:
        return existing_terminal

    decay = assess_assumption_decay(session, prediction, evaluated_at=as_of)
    if decay.verdict == VERDICT_MATERIAL_DECAY and decay.invalidation_recommended:
        event_row = PredictionOutcomeEvent(
            prediction_id=prediction.id,
            state=STATE_INVALIDATED,
            detected_at=as_of,
            observed_at=decay.evaluated_at,
            observed_price=None,
            provider=None,
            prediction_version=f"{prediction.model_version}:{decay.decay_rule_version}",
            evidence={"trigger": "assumption_decay", "assumption_decay_assessment_id": decay.id, "decay_ratio": str(decay.decay_ratio)},
            monitor_rule_version=MONITOR_RULE_VERSION,
        )
        session.add(event_row)
        session.commit()
        session.refresh(event_row)
        return event_row

    rows = list(
        session.scalars(
            select(MarketPrice)
            .where(MarketPrice.stock_id == prediction.stock_id, MarketPrice.timestamp > prediction.as_of_timestamp)
            .order_by(MarketPrice.timestamp.asc())
        ).all()
    )

    target_price, stop_loss_price, prediction_version = get_target_stop_prices(session, prediction)
    evaluation = _evaluate_bars(
        rows,
        entry_price=prediction.entry_price,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        horizon_days=prediction.horizon_days,
    )

    if evaluation is not None:
        event_row = PredictionOutcomeEvent(
            prediction_id=prediction.id,
            state=evaluation.state,
            detected_at=as_of,
            observed_at=evaluation.observed_at,
            observed_price=evaluation.observed_price,
            provider=evaluation.provider,
            prediction_version=prediction_version,
            evidence=evaluation.evidence,
            monitor_rule_version=MONITOR_RULE_VERSION,
        )
        session.add(event_row)
        session.commit()
        session.refresh(event_row)
        return event_row

    last_known_at = rows[-1].timestamp if rows else prediction.as_of_timestamp
    gap_days = (as_of.replace(tzinfo=None) - last_known_at.replace(tzinfo=None)).days
    if gap_days > STALE_BAR_GAP_DAYS and is_trading_session(as_of, holiday_dates=holiday_dates):
        history = get_event_history(session, prediction.id)
        already_flagged = (
            history
            and history[-1].state == STATE_DATA_UNRESOLVED
            and history[-1].evidence.get("last_known_at") == last_known_at.isoformat()
        )
        if not already_flagged:
            event_row = PredictionOutcomeEvent(
                prediction_id=prediction.id,
                state=STATE_DATA_UNRESOLVED,
                detected_at=as_of,
                observed_at=last_known_at,
                observed_price=None,
                provider=None,
                prediction_version=prediction_version,
                evidence={"trigger": "stale_price_data", "last_known_at": last_known_at.isoformat(), "gap_days": gap_days},
                monitor_rule_version=MONITOR_RULE_VERSION,
            )
            session.add(event_row)
            session.commit()
            session.refresh(event_row)
            return event_row

    return None

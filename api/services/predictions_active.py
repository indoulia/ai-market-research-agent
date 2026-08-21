"""Query service backing `GET /api/v1/predictions/active[/{predictionId}]`
(EPIC-M3.8).

Composes existing, already-merged domain modules -- never recomputes a
signal another EPIC owns:
  - M1.15 ``RecommendationLifecycle`` (open states) + M1.87
    ``PositiveOpportunityRanking`` (latest included batch) for the same
    "live feed" eligibility M1.135's `/recommendations` already uses --
    this is a differently-projected view of that identical universe, not
    a second, divergent definition of "active".
  - M1.119 ``app.prediction_outcome_monitor`` is the sole source of the
    ``status`` field (AC: "active state is sourced from M1.119, not
    recomputed differently in Flutter/here"). This module never decides
    for itself whether a target/stop-loss has been hit; it only reports
    the latest ``PredictionOutcomeEvent`` M1.119 already recorded (or
    ``STATE_ACTIVE`` when none exists yet). ``get_target_stop_prices`` is
    also reused verbatim from M1.119 so the absolute target/stop prices
    used for ``distanceToTargetPercent``/``distanceToStopLossPercent`` are
    identical to the ones M1.119 itself evaluates against.
  - M1.121 ``app.market_calendar.count_trading_days`` for
    ``remainingTradingDays`` -- a real trading-day count (weekends and
    registered holidays excluded), unlike M1.137's own pre-M1.121
    ``expiryAt`` field (documented there as "a naive calendar-day
    estimate ... since M1.121 hasn't landed"). Degrades gracefully (falls
    back to a weekday-only count) when no ``MarketCalendarVersion`` is
    registered for the exchange yet, since `count_trading_days` itself
    never raises for that case.
  - M1.118 ``app.schedule_orchestration`` (``classify_session`` +
    ``OPERATION_PRICE_MONITORING``'s cadence) for ``nextEvaluationAt`` --
    an honest best-effort estimate of when new price data could next move
    this prediction's status, not a guarantee a job will actually run
    then (no scheduler is wired to call M1.119 yet; see that module's own
    completion report).
  - M1.55 ``app.recommendation_revision.get_revision_history`` for
    ``lastRevisionAt``.

**Read-only, no side effects**: unlike a batch job, a GET request here
never calls `app.prediction_outcome_monitor.evaluate_prediction_realtime`
-- it only reads whatever the (separately orchestrated) monitor has
already recorded, matching this API layer's established convention (e.g.
`get_outcome` in `recommendation_detail.py` never triggers
`app.outcomes.evaluate_recommendation` either). A prediction whose
monitor hasn't been re-run since new price data arrived will show a
stale `status` until that job runs -- an inherited characteristic of the
read-only API/write-owning-job split used throughout this codebase, not
a new gap introduced here.

**Revision identity, an inherited, pre-existing limitation**: like
M1.135's own `list_recommendations`, this module joins directly from
`PositiveOpportunityRanking`/`Prediction` without resolving through
`get_active_version` first. For a prediction that has since been
revised, `lastRevisionAt` (keyed by `get_revision_history`'s
*original*-prediction-id contract) may read `None` even though a
revision exists under the new version's id. This is the same
characteristic the sibling `/recommendations` list endpoint already has;
fixing it platform-wide is out of this EPIC's scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.lifecycle import OPEN_STATES
from app.market_calendar import count_trading_days, get_holiday_dates_in_range
from app.models import (
    MarketPrice,
    Prediction,
    PositiveOpportunityRanking,
    PredictionOutcomeEvent,
    PredictionTrustScore,
    RecommendationGeneration,
    RecommendationLifecycle,
    Stock,
)
from app.prediction_outcome_monitor import STATE_ACTIVE, TERMINAL_STATES, get_target_stop_prices
from app.recommendation_revision import get_revision_history
from app.schedule_orchestration import (
    MARKET_OPEN,
    MARKET_TIMEZONE,
    OPERATION_PRICE_MONITORING,
    SESSION_MARKET_HOURS,
    SESSION_PRE_MARKET,
    TRIGGER_POLICIES,
    classify_session,
)

from ..errors import NotFoundError
from ..pagination import DEFAULT_PAGE_SIZE
from ..schemas.predictions_active import ActivePrediction
from .keyset import decode_cursor, encode_cursor, keyset_predicate

_PRICE_MONITORING_CADENCE = TRIGGER_POLICIES[OPERATION_PRICE_MONITORING].cadence


@dataclass
class ActivePredictionPage:
    items: list[ActivePrediction]
    next_cursor: str | None


def _distance_percents(
    price: Decimal | None, target_price: Decimal, stop_loss: Decimal
) -> tuple[Decimal | None, Decimal | None]:
    """% move still needed to reach target, and % buffer remaining above
    stop-loss, both measured from the current price. Negative values are
    reported as-is (not clamped) -- they honestly indicate the level has
    already been crossed on the latest available close, ahead of M1.119's
    own confirmation via `status`."""
    if price is None or price == 0:
        return None, None
    distance_to_target = (target_price - price) / price * 100
    distance_to_stop_loss = (price - stop_loss) / price * 100
    return distance_to_target, distance_to_stop_loss


def _remaining_trading_days(session: Session, exchange: str, as_of: datetime, horizon_days: int, today: date) -> int:
    as_of_date = as_of.date()
    if today <= as_of_date:
        # Not yet the trading day after entry (or clock skew) -- no
        # trading days have elapsed, so the full horizon remains.
        return horizon_days
    elapsed = count_trading_days(session, exchange, as_of_date, today)
    return max(horizon_days - elapsed, 0)


def _next_evaluation_at(session: Session, exchange: str, status: str, at: datetime) -> datetime | None:
    """`None` once a prediction has reached a terminal M1.119 state --
    nothing further will ever be evaluated for it."""
    if status in TERMINAL_STATES:
        return None

    aware_at = at if at.tzinfo is not None else at.replace(tzinfo=timezone.utc)
    local = aware_at.astimezone(MARKET_TIMEZONE)
    holiday_dates = get_holiday_dates_in_range(session, exchange, local.date(), local.date() + timedelta(days=14))
    session_state = classify_session(aware_at, holiday_dates=holiday_dates)

    if session_state == SESSION_MARKET_HOURS:
        return aware_at + _PRICE_MONITORING_CADENCE
    if session_state == SESSION_PRE_MARKET:
        return datetime.combine(local.date(), MARKET_OPEN, tzinfo=MARKET_TIMEZONE).astimezone(timezone.utc)

    for offset in range(1, 15):
        candidate_date = local.date() + timedelta(days=offset)
        if candidate_date.weekday() < 5 and candidate_date not in holiday_dates:
            return datetime.combine(candidate_date, MARKET_OPEN, tzinfo=MARKET_TIMEZONE).astimezone(timezone.utc)
    return None


def _latest_status(session: Session, prediction_id: int) -> str:
    event_row = session.scalar(
        select(PredictionOutcomeEvent)
        .where(PredictionOutcomeEvent.prediction_id == prediction_id)
        .order_by(PredictionOutcomeEvent.id.desc())
        .limit(1)
    )
    return event_row.state if event_row is not None else STATE_ACTIVE


def _last_revision_at(session: Session, original_prediction_id: int) -> datetime | None:
    history = get_revision_history(session, original_prediction_id)
    return history[-1].revised_at if history else None


def _latest_price_rows(session: Session, stock_ids: list[int]) -> dict[int, tuple[Decimal | None, datetime | None]]:
    if not stock_ids:
        return {}
    ranked = (
        select(
            MarketPrice.stock_id,
            MarketPrice.close,
            MarketPrice.timestamp,
            func.row_number().over(partition_by=MarketPrice.stock_id, order_by=MarketPrice.timestamp.desc()).label("rn"),
        )
        .where(MarketPrice.stock_id.in_(stock_ids))
        .subquery()
    )
    rows = session.execute(
        select(ranked.c.stock_id, ranked.c.close, ranked.c.timestamp).where(ranked.c.rn == 1)
    ).all()
    by_stock = {stock_id: (close, ts) for stock_id, close, ts in rows}
    return {stock_id: by_stock.get(stock_id, (None, None)) for stock_id in stock_ids}


def _latest_trust_scores(session: Session, prediction_ids: list[int]) -> dict[int, Decimal | None]:
    if not prediction_ids:
        return {}
    latest_ids = (
        select(PredictionTrustScore.prediction_id.label("prediction_id"), func.max(PredictionTrustScore.id).label("id"))
        .where(PredictionTrustScore.prediction_id.in_(prediction_ids))
        .group_by(PredictionTrustScore.prediction_id)
        .subquery()
    )
    rows = session.execute(
        select(latest_ids.c.prediction_id, PredictionTrustScore.overall_trust_score).join(
            PredictionTrustScore, PredictionTrustScore.id == latest_ids.c.id
        )
    ).all()
    scores = {prediction_id: score for prediction_id, score in rows}
    return {prediction_id: scores.get(prediction_id) for prediction_id in prediction_ids}


def list_active_predictions(
    session: Session, *, cursor: str | None = None, page_size: int = DEFAULT_PAGE_SIZE
) -> ActivePredictionPage:
    latest_evaluated_at = session.scalar(select(func.max(PositiveOpportunityRanking.evaluated_at)))
    if latest_evaluated_at is None:
        return ActivePredictionPage(items=[], next_cursor=None)

    stmt = (
        select(
            Prediction.id.label("prediction_id"),
            Prediction.stock_id,
            Prediction.horizon_days,
            Prediction.confidence,
            Prediction.as_of_timestamp,
            Stock.symbol,
            Stock.exchange,
            Stock.company_name,
            PositiveOpportunityRanking.composite_score,
        )
        .select_from(PositiveOpportunityRanking)
        .join(Prediction, Prediction.id == PositiveOpportunityRanking.prediction_id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .join(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .join(RecommendationLifecycle, RecommendationLifecycle.recommendation_generation_id == RecommendationGeneration.id)
        .where(
            PositiveOpportunityRanking.included.is_(True),
            PositiveOpportunityRanking.evaluated_at == latest_evaluated_at,
            RecommendationLifecycle.state.in_(OPEN_STATES),
        )
    )

    id_col = Prediction.id
    sort_expr = PositiveOpportunityRanking.composite_score
    if cursor:
        cursor_value, cursor_id = decode_cursor(cursor, is_datetime=False)
        if cursor_value is not None:
            stmt = stmt.where(keyset_predicate(sort_expr, id_col, cursor_value, cursor_id, descending=True))

    stmt = stmt.order_by(sort_expr.desc(), id_col.desc()).limit(page_size + 1)

    rows = session.execute(stmt).all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]

    now = datetime.now(timezone.utc)
    stock_ids = [row._mapping["stock_id"] for row in rows]
    prediction_ids = [row._mapping["prediction_id"] for row in rows]
    price_rows = _latest_price_rows(session, stock_ids)
    trust_scores = _latest_trust_scores(session, prediction_ids)

    items = []
    for row in rows:
        m = row._mapping
        target_price, stop_loss, _version = get_target_stop_prices(session, session.get(Prediction, m["prediction_id"]))
        price, last_price_at = price_rows.get(m["stock_id"], (None, None))
        distance_to_target, distance_to_stop_loss = _distance_percents(price, target_price, stop_loss)
        status = _latest_status(session, m["prediction_id"])

        items.append(
            ActivePrediction(
                predictionId=m["prediction_id"],
                symbol=m["symbol"],
                companyName=m["company_name"],
                exchange=m["exchange"],
                price=price,
                targetPrice=target_price,
                stopLoss=stop_loss,
                horizon=m["horizon_days"],
                remainingTradingDays=_remaining_trading_days(session, m["exchange"], m["as_of_timestamp"], m["horizon_days"], now.date()),
                distanceToTargetPercent=distance_to_target,
                distanceToStopLossPercent=distance_to_stop_loss,
                score=m["composite_score"],
                confidence=m["confidence"],
                trustScore=trust_scores.get(m["prediction_id"]),
                status=status,
                lastPriceAt=last_price_at,
                lastRevisionAt=_last_revision_at(session, m["prediction_id"]),
                nextEvaluationAt=_next_evaluation_at(session, m["exchange"], status, now),
            )
        )

    next_cursor = None
    if has_more and rows:
        last = rows[-1]._mapping
        next_cursor = encode_cursor(last["composite_score"], last["prediction_id"])

    return ActivePredictionPage(items=items, next_cursor=next_cursor)


def get_active_prediction(session: Session, prediction_id: int) -> ActivePrediction:
    prediction = session.get(Prediction, prediction_id)
    if prediction is None:
        raise NotFoundError("Prediction", str(prediction_id))

    stock = session.get(Stock, prediction.stock_id)
    target_price, stop_loss, _version = get_target_stop_prices(session, prediction)

    price_row = session.execute(
        select(MarketPrice.close, MarketPrice.timestamp)
        .where(MarketPrice.stock_id == prediction.stock_id)
        .order_by(MarketPrice.timestamp.desc())
        .limit(1)
    ).first()
    price, last_price_at = (price_row.close, price_row.timestamp) if price_row is not None else (None, None)
    distance_to_target, distance_to_stop_loss = _distance_percents(price, target_price, stop_loss)

    score_row = session.scalar(
        select(PositiveOpportunityRanking)
        .where(PositiveOpportunityRanking.prediction_id == prediction.id, PositiveOpportunityRanking.included.is_(True))
        .order_by(PositiveOpportunityRanking.evaluated_at.desc())
        .limit(1)
    )
    trust_row = session.scalar(
        select(PredictionTrustScore)
        .where(PredictionTrustScore.prediction_id == prediction.id)
        .order_by(PredictionTrustScore.id.desc())
        .limit(1)
    )
    status = _latest_status(session, prediction.id)
    now = datetime.now(timezone.utc)

    return ActivePrediction(
        predictionId=prediction.id,
        symbol=stock.symbol,
        companyName=stock.company_name,
        exchange=stock.exchange,
        price=price,
        targetPrice=target_price,
        stopLoss=stop_loss,
        horizon=prediction.horizon_days,
        remainingTradingDays=_remaining_trading_days(session, stock.exchange, prediction.as_of_timestamp, prediction.horizon_days, now.date()),
        distanceToTargetPercent=distance_to_target,
        distanceToStopLossPercent=distance_to_stop_loss,
        score=score_row.composite_score if score_row is not None else None,
        confidence=prediction.confidence,
        trustScore=trust_row.overall_trust_score if trust_row is not None else None,
        status=status,
        lastPriceAt=last_price_at,
        lastRevisionAt=_last_revision_at(session, prediction.id),
        nextEvaluationAt=_next_evaluation_at(session, stock.exchange, status, now),
    )

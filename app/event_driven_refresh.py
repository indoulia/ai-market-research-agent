"""EPIC-M1.106: trigger timely data refresh and prediction re-analysis
when a material external event occurs, rather than waiting only for
scheduled polling.

Routes every trigger through provider-produced evidence this platform
already ingests -- `NewsEventRecord` (M1.73, HIGH materiality only),
`CorporateAction` (M1.96), `ScanCandidate` (M1.12, for price/volume
shock) and `RegimeTransitionAssessment` (M1.102) -- rather than
inventing a second event feed. "Route triggers through provider
abstractions" (scope) is satisfied because every one of those source
tables is itself populated exclusively through this platform's own
provider adapters (M1.90/M1.91); this module never calls a provider
directly.

**Deduplication** (scope) is a real, DB-enforced unique constraint on
`(event_type, source_table, source_id)` -- the exact same underlying
news record, corporate action, or regime transition can never create a
second trigger, no matter how many times this function is called.

**Materiality thresholds** (scope): only `MATERIALITY_HIGH` news counts
as `MAJOR_NEWS` (M1.73's own vocabulary, reused unchanged); price/volume
shock uses fixed, documented, versioned thresholds distinct from (and
higher than) M1.26's own regime-classification volatility threshold --
a "shock" for an individual candidate is a materially different
question from "is the market, in aggregate, in a high-volatility
regime today."

**Refresh-storm prevention** (scope): before re-running M1.105's
`evaluate_prediction_freshness` for an affected, still-open prediction,
this module checks that prediction's own freshness history for a
decision already made within `REFRESH_COOLDOWN` of `as_of` -- if one
exists, that prediction is skipped for this trigger round entirely
(not merely deduplicated per event, but rate-limited per prediction
across ALL events), so a burst of several qualifying events for the
same stock in a short window still produces at most one fresh
re-analysis per prediction per cooldown window.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    CorporateAction,
    EventTriggerRecord,
    NewsEventRecord,
    Prediction,
    RecommendationGeneration,
    RegimeTransitionAssessment,
    ScanCandidate,
)
from .news_data.ingest import MATERIALITY_HIGH
from .prediction_freshness_engine import evaluate_prediction_freshness, get_freshness_history
from .recommendation_generator import OUTCOME_QUALIFIED

EVENT_TRIGGER_VERSION = "EDR-001"

EVENT_MAJOR_NEWS = "MAJOR_NEWS"
EVENT_CORPORATE_ACTION = "CORPORATE_ACTION"
EVENT_PRICE_VOLUME_SHOCK = "PRICE_VOLUME_SHOCK"
EVENT_REGIME_CHANGE = "REGIME_CHANGE"

SOURCE_NEWS = "news_event_records"
SOURCE_CORPORATE_ACTION = "corporate_actions"
SOURCE_SCAN_CANDIDATE = "scan_candidates"
SOURCE_REGIME_TRANSITION = "regime_transition_assessments"

# Fixed, documented, versioned policy thresholds for an individual
# candidate's own price/volume shock -- distinct from (and stricter
# than) M1.26's market-wide high-volatility regime threshold, since a
# shock for one stock is a different question from the market's
# aggregate regime.
SHOCK_VOLUME_RATIO_THRESHOLD = Decimal("3.0")
SHOCK_ATR_PERCENT_THRESHOLD = Decimal("0.08")

# A prediction re-analyzed within this window of `as_of` is not
# re-analyzed again for a subsequent trigger in the same window --
# prevents a burst of qualifying events from causing a refresh storm.
REFRESH_COOLDOWN = timedelta(hours=1)


def _record_trigger(
    session: Session, *, stock_id: int, event_type: str, source_table: str, source_id: str,
    detected_at: datetime, materiality_note: str | None,
) -> EventTriggerRecord | None:
    existing = session.scalar(
        select(EventTriggerRecord).where(
            EventTriggerRecord.event_type == event_type, EventTriggerRecord.source_table == source_table,
            EventTriggerRecord.source_id == source_id,
        )
    )
    if existing is not None:
        return None

    trigger = EventTriggerRecord(
        stock_id=stock_id, event_type=event_type, source_table=source_table, source_id=source_id,
        detected_at=detected_at, materiality_note=materiality_note, affected_prediction_count=0,
        triggered_decision_ids=[], processed_at=None, trigger_rule_version=EVENT_TRIGGER_VERSION,
    )
    session.add(trigger)
    session.commit()
    session.refresh(trigger)
    return trigger


def _detect_new_triggers(session: Session, stock_id: int) -> list[EventTriggerRecord]:
    triggers: list[EventTriggerRecord] = []

    for news in session.scalars(
        select(NewsEventRecord).where(NewsEventRecord.stock_id == stock_id, NewsEventRecord.materiality == MATERIALITY_HIGH)
    ).all():
        trigger = _record_trigger(
            session, stock_id=stock_id, event_type=EVENT_MAJOR_NEWS, source_table=SOURCE_NEWS, source_id=str(news.id),
            detected_at=news.published_at, materiality_note=news.event_type,
        )
        if trigger is not None:
            triggers.append(trigger)

    for action in session.scalars(select(CorporateAction).where(CorporateAction.stock_id == stock_id)).all():
        trigger = _record_trigger(
            session, stock_id=stock_id, event_type=EVENT_CORPORATE_ACTION, source_table=SOURCE_CORPORATE_ACTION,
            source_id=str(action.id), detected_at=action.recorded_at, materiality_note=action.action_type,
        )
        if trigger is not None:
            triggers.append(trigger)

    for candidate in session.scalars(
        select(ScanCandidate).where(
            ScanCandidate.stock_id == stock_id,
            (ScanCandidate.volume_ratio_20d >= SHOCK_VOLUME_RATIO_THRESHOLD) | (ScanCandidate.atr_percent >= SHOCK_ATR_PERCENT_THRESHOLD),
        )
    ).all():
        trigger = _record_trigger(
            session, stock_id=stock_id, event_type=EVENT_PRICE_VOLUME_SHOCK, source_table=SOURCE_SCAN_CANDIDATE,
            source_id=str(candidate.id), detected_at=candidate.created_at, materiality_note=None,
        )
        if trigger is not None:
            triggers.append(trigger)

    scan_ids = set(
        session.scalars(
            select(ScanCandidate.scan_id)
            .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
            .where(ScanCandidate.stock_id == stock_id, RecommendationGeneration.outcome == OUTCOME_QUALIFIED)
        ).all()
    )
    if scan_ids:
        for regime in session.scalars(
            select(RegimeTransitionAssessment).where(
                RegimeTransitionAssessment.scan_id.in_(scan_ids), RegimeTransitionAssessment.transition_detected.is_(True)
            )
        ).all():
            trigger = _record_trigger(
                session, stock_id=stock_id, event_type=EVENT_REGIME_CHANGE, source_table=SOURCE_REGIME_TRANSITION,
                source_id=str(regime.id), detected_at=regime.detected_at,
                materiality_note=f"{regime.previous_regime}->{regime.current_regime}",
            )
            if trigger is not None:
                triggers.append(trigger)

    return triggers


def _recently_reanalyzed(session: Session, prediction_id: int, *, as_of: datetime) -> bool:
    history = get_freshness_history(session, prediction_id)
    if not history:
        return False
    latest = history[-1]
    age = as_of.replace(tzinfo=None) - latest.evaluated_at.replace(tzinfo=None)
    return age < REFRESH_COOLDOWN


def process_event_triggers_for_stock(session: Session, stock_id: int, *, as_of: datetime) -> tuple[EventTriggerRecord, ...]:
    """Detects every not-yet-recorded qualifying event for `stock_id`,
    then revalidates this stock's still-open predictions at most once
    per prediction within `REFRESH_COOLDOWN` of `as_of`, regardless of
    how many new triggers fired in this call."""
    new_triggers = _detect_new_triggers(session, stock_id)
    if not new_triggers:
        return ()

    open_predictions = list(
        session.scalars(select(Prediction).where(Prediction.stock_id == stock_id, Prediction.status == "OPEN")).all()
    )

    decision_ids: list[int] = []
    for prediction in open_predictions:
        if _recently_reanalyzed(session, prediction.id, as_of=as_of):
            continue
        decision = evaluate_prediction_freshness(session, prediction, evaluated_at=as_of)
        decision_ids.append(decision.id)

    for trigger in new_triggers:
        trigger.affected_prediction_count = len(decision_ids)
        trigger.triggered_decision_ids = list(decision_ids)
        trigger.processed_at = as_of
    session.commit()
    for trigger in new_triggers:
        session.refresh(trigger)

    return tuple(new_triggers)


def get_trigger_history(session: Session, stock_id: int) -> tuple[EventTriggerRecord, ...]:
    return tuple(
        session.scalars(
            select(EventTriggerRecord).where(EventTriggerRecord.stock_id == stock_id).order_by(EventTriggerRecord.id.asc())
        ).all()
    )

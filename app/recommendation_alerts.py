"""EPIC-M1.63: notify users only when a recommendation or market event
requires attention -- never as a side effect of, and never causing, any
change to a recommendation itself (AC: "no recommendation is changed
merely because an alert is sent" -- this module has no write path to
`Prediction` or any scoring/selection table at all).

Each alert-creating function takes an already-produced source event
(M1.62's `RecommendationRevalidationOutcome`, M1.26's `MarketRegime`, or
M1.14's `RecommendationSelection`) rather than scanning for one itself,
matching this platform's established compositional style -- this module
never recomputes any of them.

Deduplication is structural, not a heuristic: `RecommendationAlert` is
unique-constrained on `(user_id, alert_type, source_table, source_id)`, so
the same underlying event can never generate a second alert for the same
user, no matter how many times the corresponding create-function is called
(AC: "duplicate alerts are suppressed"). Severity is a fixed, deterministic
mapping per alert type (AC: "alert severity is deterministic").

`UserAlertPreference` is versioned and append-only, mirroring M1.46/M1.60's
own preference pattern (AC: "users can control alert preferences") -- a
muted alert type is skipped before any row is even considered, not merely
hidden after the fact.

`ALERT_TYPE_MAJOR_NEWS_EVENT` is defined for forward compatibility but never
triggered anywhere in this module: this repo has no real news/event feed to
trigger it from honestly (the same gap M1.35/M1.48 already documented for
fundamental/event evidence).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import MarketRegime, RecommendationAlert, RecommendationGeneration, RecommendationRevalidationOutcome, RecommendationSelection, UserAlertPreference
from .recommendation_revalidation import OUTCOME_EXPIRED, OUTCOME_UNCHANGED, OUTCOME_UPDATED, OUTCOME_WITHDRAWN

ALERT_PREFERENCE_VERSION = "UAP-001"
ALERT_RULE_VERSION = "RAL-001"

ALERT_TYPE_EXPIRY = "EXPIRY"
ALERT_TYPE_INVALIDATION = "INVALIDATION"
ALERT_TYPE_REVALIDATION_UPDATE = "REVALIDATION_UPDATE"
ALERT_TYPE_MARKET_REGIME_CHANGE = "MARKET_REGIME_CHANGE"
ALERT_TYPE_NEW_OPPORTUNITY = "NEW_OPPORTUNITY"
ALERT_TYPE_MAJOR_NEWS_EVENT = "MAJOR_NEWS_EVENT"  # reserved; no real trigger source exists in this repo yet

SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"

_SEVERITY_BY_ALERT_TYPE = {
    ALERT_TYPE_EXPIRY: SEVERITY_LOW,
    ALERT_TYPE_INVALIDATION: SEVERITY_HIGH,
    ALERT_TYPE_REVALIDATION_UPDATE: SEVERITY_MEDIUM,
    ALERT_TYPE_MARKET_REGIME_CHANGE: SEVERITY_MEDIUM,
    ALERT_TYPE_NEW_OPPORTUNITY: SEVERITY_MEDIUM,
    ALERT_TYPE_MAJOR_NEWS_EVENT: SEVERITY_HIGH,
}

_OUTCOME_TO_ALERT_TYPE = {
    OUTCOME_EXPIRED: ALERT_TYPE_EXPIRY,
    OUTCOME_WITHDRAWN: ALERT_TYPE_INVALIDATION,
    OUTCOME_UPDATED: ALERT_TYPE_REVALIDATION_UPDATE,
}


class UserAlertPreferenceImmutableError(RuntimeError):
    pass


IMMUTABLE_ALERT_PREFERENCE_FIELDS = ("user_id", "muted_alert_types", "effective_at", "alert_preference_rule_version", "created_at")


@event.listens_for(UserAlertPreference, "before_update")
def _reject_preference_update(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in IMMUTABLE_ALERT_PREFERENCE_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise UserAlertPreferenceImmutableError(f"user alert preference {target.id} field(s) {changed} cannot be modified after creation")


class RecommendationAlertImmutableError(RuntimeError):
    pass


IMMUTABLE_ALERT_FIELDS = (
    "user_id", "alert_type", "severity", "prediction_id", "source_table", "source_id",
    "message", "triggered_at", "alert_rule_version", "created_at",
)


@event.listens_for(RecommendationAlert, "before_update")
def _reject_alert_update(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in IMMUTABLE_ALERT_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise RecommendationAlertImmutableError(f"recommendation alert {target.id} field(s) {changed} cannot be modified after creation")


def set_alert_preference(
    session: Session, *, user_id: str, muted_alert_types: list, effective_at: datetime
) -> UserAlertPreference:
    """Always inserts a new version -- never mutates a prior one (the same
    pattern M1.46/M1.60 already established)."""
    preference = UserAlertPreference(
        user_id=user_id, muted_alert_types=list(muted_alert_types), effective_at=effective_at,
        alert_preference_rule_version=ALERT_PREFERENCE_VERSION,
    )
    session.add(preference)
    session.commit()
    session.refresh(preference)
    return preference


def get_current_alert_preference(session: Session, user_id: str, *, effective_at: datetime) -> UserAlertPreference:
    existing = session.scalar(
        select(UserAlertPreference).where(UserAlertPreference.user_id == user_id).order_by(UserAlertPreference.id.desc())
    )
    if existing is not None:
        return existing
    return set_alert_preference(session, user_id=user_id, muted_alert_types=[], effective_at=effective_at)


def _existing_alert(session: Session, *, user_id: str, alert_type: str, source_table: str, source_id: int) -> RecommendationAlert | None:
    return session.scalar(
        select(RecommendationAlert).where(
            RecommendationAlert.user_id == user_id,
            RecommendationAlert.alert_type == alert_type,
            RecommendationAlert.source_table == source_table,
            RecommendationAlert.source_id == source_id,
        )
    )


def _create_alert(
    session: Session, *, user_id: str, alert_type: str, prediction_id: int | None,
    source_table: str, source_id: int, message: str, triggered_at: datetime,
) -> RecommendationAlert | None:
    """Returns `None` without writing anything if this alert type is muted
    for this user, or if this exact source event was already alerted on
    (structural deduplication, not a heuristic)."""
    preference = get_current_alert_preference(session, user_id, effective_at=triggered_at)
    if alert_type in preference.muted_alert_types:
        return None

    existing = _existing_alert(session, user_id=user_id, alert_type=alert_type, source_table=source_table, source_id=source_id)
    if existing is not None:
        return existing

    alert = RecommendationAlert(
        user_id=user_id, alert_type=alert_type, severity=_SEVERITY_BY_ALERT_TYPE[alert_type],
        prediction_id=prediction_id, source_table=source_table, source_id=source_id,
        message=message, triggered_at=triggered_at, alert_rule_version=ALERT_RULE_VERSION,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def create_alert_from_revalidation(
    session: Session, *, user_id: str, revalidation_outcome: RecommendationRevalidationOutcome, triggered_at: datetime
) -> RecommendationAlert | None:
    """No alert for `UNCHANGED` -- not every check needs to notify anyone
    (AC: "alerts are tied to explicit events", not to every check run)."""
    if revalidation_outcome.outcome == OUTCOME_UNCHANGED:
        return None
    alert_type = _OUTCOME_TO_ALERT_TYPE[revalidation_outcome.outcome]
    return _create_alert(
        session, user_id=user_id, alert_type=alert_type, prediction_id=revalidation_outcome.prediction_id,
        source_table="recommendation_revalidation_outcomes", source_id=revalidation_outcome.id,
        message=revalidation_outcome.reason, triggered_at=triggered_at,
    )


def create_alert_from_regime_change(
    session: Session, *, user_id: str, previous_regime: MarketRegime, current_regime: MarketRegime, triggered_at: datetime
) -> RecommendationAlert | None:
    if previous_regime.regime == current_regime.regime:
        return None
    return _create_alert(
        session, user_id=user_id, alert_type=ALERT_TYPE_MARKET_REGIME_CHANGE, prediction_id=None,
        source_table="market_regimes", source_id=current_regime.id,
        message=f"market regime changed from {previous_regime.regime} to {current_regime.regime}",
        triggered_at=triggered_at,
    )


def create_alert_from_new_opportunity(
    session: Session, *, user_id: str, selection: RecommendationSelection, triggered_at: datetime
) -> RecommendationAlert | None:
    if not selection.selected:
        return None
    prediction_id = session.scalar(
        select(RecommendationGeneration.prediction_id).where(RecommendationGeneration.id == selection.recommendation_generation_id)
    )
    return _create_alert(
        session, user_id=user_id, alert_type=ALERT_TYPE_NEW_OPPORTUNITY, prediction_id=prediction_id,
        source_table="recommendation_selections", source_id=selection.id,
        message=f"new high-confidence opportunity selected (rank {selection.rank})",
        triggered_at=triggered_at,
    )


def get_alert_history(session: Session, user_id: str) -> tuple[RecommendationAlert, ...]:
    return tuple(
        session.scalars(
            select(RecommendationAlert).where(RecommendationAlert.user_id == user_id).order_by(RecommendationAlert.id.asc())
        ).all()
    )

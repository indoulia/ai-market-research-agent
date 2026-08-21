"""EPIC-M1.70: learn stable user preferences from repeated behavior while
keeping M1.46's explicit `UserPreference` authoritative.

"Observe accepted/rejected recommendation patterns" (scope) uses the only
real, already-existing signal of a user's own reaction to a specific
recommendation: M1.52's `RecommendationFeedback` -- `REASON_AGREE` is
treated as "accepted", any other valid reason code as "rejected". This
module does not fabricate a dedicated accept/reject button that does not
exist in this platform yet; it reuses what users already do.

This module has no write path to `UserPreference`, `Prediction`,
`ScanCandidate`, or any scoring/selection table at all -- it only ever
reads them and writes to its own, brand-new `UserPreferenceSuggestion`
table (AC: "personal learning cannot modify the global production
model"). `app.user_preferences.apply_preferences_to_scan_selection` never
reads `UserPreferenceSuggestion`, so a suggestion can only ever take
effect if the user explicitly calls `set_user_preference` themselves (AC:
"explicit settings always override inferred preferences").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import Prediction, RecommendationFeedback, UserPreference, UserPreferenceSuggestion
from .recommendation_feedback import REASON_AGREE
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON
from .user_preferences import HORIZON_BAND_DAY_RANGES

PREFERENCE_LEARNING_VERSION = "UPL-001"

# Fixed, documented, versioned policy constant: the best-supported band's
# agreement rate must exceed the user's current band's by at least this
# much before a suggestion is worth surfacing -- a small edge is noise, not
# a stable preference signal (AC: "minimum evidence thresholds are
# explicit").
PREFERENCE_SIGNAL_MARGIN = Decimal("0.20")


class UserPreferenceSuggestionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "user_id",
    "current_horizon_band",
    "suggested_horizon_band",
    "evidence_sample_count",
    "evidence_agree_rate",
    "current_band_agree_rate",
    "rationale",
    "suggested_at",
    "learning_rule_version",
    "created_at",
)


@event.listens_for(UserPreferenceSuggestion, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise UserPreferenceSuggestionImmutableError(
            f"user preference suggestion {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class HorizonBandFeedbackSignal:
    horizon_band: str
    total_feedback_count: int
    agree_count: int
    agree_rate: Decimal | None


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _band_for_horizon(horizon_days: int) -> str | None:
    for band, (lower, upper) in HORIZON_BAND_DAY_RANGES.items():
        if horizon_days < lower:
            continue
        if upper is None or horizon_days <= upper:
            return band
    return None


def observe_horizon_band_feedback(session: Session, user_id: str) -> tuple[HorizonBandFeedbackSignal, ...]:
    """Aggregates every feedback event this user has ever given, grouped by
    which of M1.46's fixed horizon bands the underlying prediction's
    `horizon_days` falls into (scope: "observe accepted/rejected
    recommendation patterns")."""
    rows = session.execute(
        select(RecommendationFeedback, Prediction)
        .join(Prediction, Prediction.id == RecommendationFeedback.prediction_id)
        .where(RecommendationFeedback.user_id == user_id)
    ).all()

    agreements_by_band: dict[str, list[bool]] = {band: [] for band in HORIZON_BAND_DAY_RANGES}
    for feedback, prediction in rows:
        band = _band_for_horizon(prediction.horizon_days)
        if band is None:
            continue
        agreements_by_band[band].append(feedback.reason_code == REASON_AGREE)

    signals = []
    for band in HORIZON_BAND_DAY_RANGES:
        agreements = agreements_by_band[band]
        agree_count = sum(1 for a in agreements if a)
        signals.append(
            HorizonBandFeedbackSignal(
                horizon_band=band,
                total_feedback_count=len(agreements),
                agree_count=agree_count,
                agree_rate=_rate(agree_count, len(agreements)),
            )
        )
    return tuple(signals)


def _latest_preference_readonly(session: Session, user_id: str) -> UserPreference | None:
    return session.scalar(
        select(UserPreference).where(UserPreference.user_id == user_id).order_by(UserPreference.id.desc())
    )


def generate_preference_suggestion(
    session: Session, user_id: str, *, as_of: datetime
) -> UserPreferenceSuggestion | None:
    """Detects a stable preference signal (scope item 2) and, only if one
    exists, persists a suggestion (scope item 3) -- never applies it (AC:
    "never silently alter explicit user settings"). Returns `None` when
    evidence is insufficient or the user's current band already best
    matches their own revealed behavior."""
    current = _latest_preference_readonly(session, user_id)
    current_band = current.horizon_band if current is not None else None

    signals = observe_horizon_band_feedback(session, user_id)
    eligible = [s for s in signals if s.total_feedback_count >= MIN_SAMPLE_SIZE_FOR_COMPARISON and s.agree_rate is not None]
    if not eligible:
        return None

    best = max(eligible, key=lambda s: s.agree_rate)
    if best.horizon_band == current_band:
        return None

    current_signal = next((s for s in eligible if s.horizon_band == current_band), None)
    current_rate = current_signal.agree_rate if current_signal is not None else Decimal("0")
    if best.agree_rate - current_rate < PREFERENCE_SIGNAL_MARGIN:
        return None

    rationale = (
        f"Over {best.total_feedback_count} feedback events on {best.horizon_band}-horizon recommendations, "
        f"you agreed {best.agree_rate:.2%} of the time"
        + (
            f", versus {current_rate:.2%} on your current {current_band} band"
            if current_signal is not None
            else f"; your current preference ({current_band or 'unset'}) has no comparable feedback evidence"
        )
        + " -- a stable, repeated pattern rather than a single opinion."
    )

    suggestion = UserPreferenceSuggestion(
        user_id=user_id,
        current_horizon_band=current_band,
        suggested_horizon_band=best.horizon_band,
        evidence_sample_count=best.total_feedback_count,
        evidence_agree_rate=best.agree_rate,
        current_band_agree_rate=current_signal.agree_rate if current_signal is not None else None,
        rationale=rationale,
        suggested_at=as_of,
        learning_rule_version=PREFERENCE_LEARNING_VERSION,
    )
    session.add(suggestion)
    session.commit()
    session.refresh(suggestion)
    return suggestion


def get_suggestions_for_user(session: Session, user_id: str) -> tuple[UserPreferenceSuggestion, ...]:
    return tuple(
        session.scalars(
            select(UserPreferenceSuggestion)
            .where(UserPreferenceSuggestion.user_id == user_id)
            .order_by(UserPreferenceSuggestion.id.asc())
        ).all()
    )

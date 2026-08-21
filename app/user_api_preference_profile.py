"""EPIC-M1.141: persists the preference fields the API contract needs
(`markets`, `industries`, `watchlist`, `notificationPreferences`,
`displayPreferences`) that have no existing domain home. Mirrors
`app.user_preferences.UserPreference`'s exact pattern -- an append-only
log where the most recent row per `user_id` is the current effective
value, so a preference change is always a new insert, never a mutation
of history.

`app.user_preferences.UserPreference` already owns horizon/risk/sector/
market-cap-bucket preferences (EPIC-M1.46) and is reused unchanged for
those; this module only covers what that one doesn't.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import UserApiPreferenceProfile

API_PREFERENCE_PROFILE_VERSION = "UPP-001"

VALID_MARKETS = frozenset({"NSE", "BSE"})


class InvalidApiPreferenceProfileError(ValueError):
    pass


class UserApiPreferenceProfileImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "user_id",
    "markets",
    "industries",
    "watchlist_symbols",
    "notification_preferences",
    "display_preferences",
    "effective_at",
    "preference_rule_version",
    "created_at",
)


@event.listens_for(UserApiPreferenceProfile, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise UserApiPreferenceProfileImmutableError(
            f"api preference profile {target.id} field(s) {changed} cannot be modified after creation -- set a new profile instead"
        )


def _validate(markets: list[str]) -> None:
    invalid = set(markets) - VALID_MARKETS
    if invalid:
        raise InvalidApiPreferenceProfileError(f"markets contains unknown value(s): {sorted(invalid)}")


def set_api_preference_profile(
    session: Session,
    *,
    user_id: str,
    effective_at: datetime,
    markets: list[str] | None = None,
    industries: list[str] | None = None,
    watchlist_symbols: list[str] | None = None,
    notification_preferences: dict | None = None,
    display_preferences: dict | None = None,
) -> UserApiPreferenceProfile:
    markets = markets if markets is not None else []
    _validate(markets)
    profile = UserApiPreferenceProfile(
        user_id=user_id,
        markets=markets,
        industries=industries if industries is not None else [],
        watchlist_symbols=watchlist_symbols if watchlist_symbols is not None else [],
        notification_preferences=notification_preferences if notification_preferences is not None else {},
        display_preferences=display_preferences if display_preferences is not None else {},
        effective_at=effective_at,
        preference_rule_version=API_PREFERENCE_PROFILE_VERSION,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def get_current_api_preference_profile(session: Session, user_id: str, *, effective_at: datetime) -> UserApiPreferenceProfile:
    """Returns the most recent profile for `user_id`, or lazily creates and
    returns a real, persisted, all-empty default if this user has never
    set one -- idempotent, matching `UserPreference.get_current_preference`."""
    existing = session.scalar(
        select(UserApiPreferenceProfile).where(UserApiPreferenceProfile.user_id == user_id).order_by(UserApiPreferenceProfile.id.desc())
    )
    if existing is not None:
        return existing
    return set_api_preference_profile(session, user_id=user_id, effective_at=effective_at)

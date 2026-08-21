"""Query/update service backing GET/PUT /api/v1/preferences (EPIC-M1.141).

Composes three existing/new domain modules into one API document:
  - M1.46 `app.user_preferences` (horizon/risk/min-confidence/sectors/
    market-cap-buckets) -- reused unchanged.
  - M1.60 `app.recommendation_alerts` (`UserAlertPreference.muted_alert_
    types`) for `notificationPreferences`.
  - This EPIC's own `app.user_api_preference_profile` (markets/
    industries/watchlist/display preferences) -- the fields neither of
    the above owns.

`defaultHorizon` (a single day count) is a deliberate simplification of
M1.46's richer `horizon_band` concept: every PUT sets
`horizon_band=CUSTOM, custom_horizon_days=defaultHorizon` so the value
round-trips exactly; a user who has never called PUT sees the band's
lower bound as a sensible default (e.g. SHORT -> 1).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.recommendation_alerts import get_current_alert_preference, set_alert_preference
from app.user_api_preference_profile import InvalidApiPreferenceProfileError, get_current_api_preference_profile, set_api_preference_profile
from app.user_preferences import (
    HORIZON_BAND_CUSTOM,
    HORIZON_BAND_DAY_RANGES,
    VALID_RISK_PREFERENCES,
    InvalidPreferenceError,
    get_current_preference,
    set_user_preference,
)

from ..errors import ValidationError
from ..schemas.preferences import DisplayPreferences, NotificationPreferences, PreferencesDocument, PreferencesUpdateRequest


def _default_horizon(preference) -> int:
    if preference.horizon_band == HORIZON_BAND_CUSTOM:
        return preference.custom_horizon_days
    return HORIZON_BAND_DAY_RANGES[preference.horizon_band][0]


def get_preferences(session: Session, user_id: str, *, at: datetime) -> PreferencesDocument:
    preference = get_current_preference(session, user_id, effective_at=at)
    profile = get_current_api_preference_profile(session, user_id, effective_at=at)
    alert_preference = get_current_alert_preference(session, user_id, effective_at=at)

    return PreferencesDocument(
        defaultHorizon=_default_horizon(preference),
        markets=list(profile.markets),
        sectors=list(preference.preferred_sectors or []),
        industries=list(profile.industries),
        marketCapBuckets=list(preference.preferred_market_cap_buckets or []),
        watchlist=list(profile.watchlist_symbols),
        notificationPreferences=NotificationPreferences(mutedAlertTypes=list(alert_preference.muted_alert_types)),
        displayPreferences=DisplayPreferences(**profile.display_preferences),
        riskPreference=preference.risk_preference,
        minConfidenceThreshold=preference.min_confidence_threshold,
        preferenceVersion=f"{preference.preference_rule_version}+{profile.preference_rule_version}",
    )


def update_preferences(session: Session, user_id: str, request: PreferencesUpdateRequest, *, at: datetime) -> PreferencesDocument:
    current = get_current_preference(session, user_id, effective_at=at)
    risk_preference = request.riskPreference if request.riskPreference is not None else current.risk_preference
    if risk_preference not in VALID_RISK_PREFERENCES:
        raise ValidationError(
            f"riskPreference must be one of {VALID_RISK_PREFERENCES}, got {risk_preference!r}",
            field_errors={"riskPreference": f"must be one of {VALID_RISK_PREFERENCES}"},
        )

    try:
        set_user_preference(
            session,
            user_id=user_id,
            effective_at=at,
            horizon_band=HORIZON_BAND_CUSTOM,
            custom_horizon_days=request.defaultHorizon,
            risk_preference=risk_preference,
            min_confidence_threshold=current.min_confidence_threshold,
            preferred_sectors=request.sectors,
            preferred_market_cap_buckets=request.marketCapBuckets,
        )
    except InvalidPreferenceError as exc:
        raise ValidationError(str(exc)) from exc

    try:
        set_api_preference_profile(
            session,
            user_id=user_id,
            effective_at=at,
            markets=request.markets,
            industries=request.industries,
            watchlist_symbols=request.watchlist,
            notification_preferences=request.notificationPreferences.model_dump(),
            display_preferences=request.displayPreferences.model_dump(),
        )
    except InvalidApiPreferenceProfileError as exc:
        raise ValidationError(str(exc)) from exc

    set_alert_preference(
        session, user_id=user_id, muted_alert_types=request.notificationPreferences.mutedAlertTypes, effective_at=at,
    )

    return get_preferences(session, user_id, at=at)

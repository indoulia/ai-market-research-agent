"""DTOs for GET/PUT /api/v1/preferences (EPIC-M1.141)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Bounds an arbitrary client-supplied tag (market/sector/watchlist symbol/etc.) so a
# request body can't carry unboundedly large strings or list lengths into the DB.
_Tag = Annotated[str, StringConstraints(max_length=64)]
_MAX_TAGS = 200


class NotificationPreferences(BaseModel):
    mutedAlertTypes: list[_Tag] = Field(default_factory=list, max_length=_MAX_TAGS)


class DisplayPreferences(BaseModel):
    """Free-form key/value display settings (e.g. theme, density). No
    domain module owns display concerns, so this is validated only as a
    JSON object -- values are opaque to the API layer."""

    model_config = {"extra": "allow"}


class PreferencesDocument(BaseModel):
    defaultHorizon: int
    markets: list[str]
    sectors: list[str]
    industries: list[str]
    marketCapBuckets: list[str]
    watchlist: list[str]
    notificationPreferences: NotificationPreferences
    displayPreferences: DisplayPreferences
    riskPreference: str
    minConfidenceThreshold: Decimal
    preferenceVersion: str


class PreferencesUpdateRequest(BaseModel):
    defaultHorizon: int
    markets: list[_Tag] = Field(default_factory=list, max_length=_MAX_TAGS)
    sectors: list[_Tag] = Field(default_factory=list, max_length=_MAX_TAGS)
    industries: list[_Tag] = Field(default_factory=list, max_length=_MAX_TAGS)
    marketCapBuckets: list[_Tag] = Field(default_factory=list, max_length=_MAX_TAGS)
    watchlist: list[_Tag] = Field(default_factory=list, max_length=_MAX_TAGS)
    notificationPreferences: NotificationPreferences = Field(default_factory=NotificationPreferences)
    displayPreferences: DisplayPreferences = Field(default_factory=DisplayPreferences)
    riskPreference: str | None = None

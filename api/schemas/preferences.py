"""DTOs for GET/PUT /api/v1/preferences (EPIC-M1.141)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class NotificationPreferences(BaseModel):
    mutedAlertTypes: list[str] = Field(default_factory=list)


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
    markets: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    marketCapBuckets: list[str] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    notificationPreferences: NotificationPreferences = Field(default_factory=NotificationPreferences)
    displayPreferences: DisplayPreferences = Field(default_factory=DisplayPreferences)
    riskPreference: str | None = None

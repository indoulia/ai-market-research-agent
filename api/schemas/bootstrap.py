"""DTOs for GET /api/v1/app/bootstrap (EPIC-M1.132)."""

from __future__ import annotations

from pydantic import BaseModel


class ServerTime(BaseModel):
    utc: str


class ApiCapabilities(BaseModel):
    recommendations: bool
    discovery: bool
    marketSummary: bool
    news: bool
    events: bool
    feedback: bool
    preferences: bool
    auth: bool
    analytics: bool
    dashboard: bool


class BootstrapResponse(BaseModel):
    apiVersion: str
    contractVersion: str
    serverTime: ServerTime
    capabilities: ApiCapabilities

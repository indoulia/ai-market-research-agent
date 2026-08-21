"""DTO for GET /api/v1/version (EPIC-M3.1)."""

from __future__ import annotations

from pydantic import BaseModel


class VersionResponse(BaseModel):
    apiVersion: str
    contractVersion: str

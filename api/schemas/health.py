"""DTOs for GET /api/v1/health (EPIC-M1.132)."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    component: str
    apiVersion: str

"""Canonical envelope DTOs shared by every /api/v1 endpoint (EPIC-M1.132)."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    requestId: str
    timestamp: datetime


class PageMeta(Meta):
    page: int
    pageSize: int
    totalItems: int
    totalPages: int


class SuccessEnvelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


class PaginatedEnvelope(BaseModel, Generic[T]):
    data: list[T]
    meta: PageMeta


class CursorMeta(Meta):
    pageSize: int
    nextCursor: str | None = None


class CursorEnvelope(BaseModel, Generic[T]):
    data: list[T]
    meta: CursorMeta


class ErrorBody(BaseModel):
    code: str = Field(examples=["MRA_NOT_FOUND"])
    message: str
    details: dict = Field(default_factory=dict)
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    meta: Meta

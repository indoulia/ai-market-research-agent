"""Wires the /api/v1 BFF layer into a FastAPI application (EPIC-M1.132)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from .exception_handlers import register_exception_handlers
from .middleware import RequestContextMiddleware
from .routers import bootstrap, discovery, health, market, news_events, recommendation_detail, recommendations
from .versioning import API_PREFIX

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(bootstrap.router)
api_router.include_router(recommendations.router)
api_router.include_router(recommendation_detail.router)
api_router.include_router(discovery.router)
api_router.include_router(market.router)
api_router.include_router(news_events.router)


def register_api(app: FastAPI) -> None:
    """Mount the versioned API contract onto ``app``.

    Safe to call once per application instance. Existing routes on ``app``
    (e.g. the legacy ``/health`` and ``/api/models`` endpoints) are left
    untouched; they are not part of the ``/api/v1`` contract.
    """
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)

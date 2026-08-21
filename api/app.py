"""Wires the /api/v1 BFF layer into a FastAPI application (EPIC-M1.132)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.settings import settings

from .exception_handlers import register_exception_handlers
from .middleware import RequestContextMiddleware
from .request_logging import configure_request_logging
from .routers import auth, bootstrap, discovery, health, market, news_events, preferences, recommendation_detail, recommendations
from .versioning import API_PREFIX

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(bootstrap.router)
api_router.include_router(recommendations.router)
api_router.include_router(recommendation_detail.router)
api_router.include_router(discovery.router)
api_router.include_router(market.router)
api_router.include_router(news_events.router)
api_router.include_router(preferences.router)
api_router.include_router(auth.router)


def register_api(app: FastAPI) -> None:
    """Mount the versioned API contract onto ``app``.

    Safe to call once per application instance. Existing routes on ``app``
    (e.g. the legacy ``/health`` and ``/api/models`` endpoints) are left
    untouched; they are not part of the ``/api/v1`` contract.
    """
    configure_request_logging()
    origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)

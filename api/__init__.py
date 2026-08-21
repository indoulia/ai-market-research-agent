"""Versioned BFF API layer (EPIC-M1.132).

This package is the ONLY boundary the Flutter application is allowed to
depend on. It never imports SQLAlchemy models directly into response
shapes -- every response is a Pydantic DTO defined under ``api.schemas``.
Internal domain logic lives in ``app``; this package translates between
that domain and the stable, versioned wire contract under ``/api/v1``.
"""

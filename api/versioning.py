"""API version and compatibility rules (EPIC-M1.132).

Rules (see docs/api/VERSIONING.md for the full policy):
  - All contracts live under ``/api/{API_VERSION}``.
  - Additive, backward-compatible changes (new optional fields, new
    endpoints, new enum values consumers must tolerate) ship in-place
    within the current version.
  - Breaking changes (removed/renamed fields, changed types, removed
    endpoints, stricter validation) require a new version namespace
    (``/api/v2``) rather than mutating ``/api/v1`` in place.
  - A deprecated contract is announced via the ``Deprecation`` and
    ``Sunset`` response headers before removal, never removed silently.
"""

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"
CONTRACT_VERSION = "2026-08-21"


def deprecation_headers(sunset_date: str | None = None) -> dict[str, str]:
    """Standard headers for an endpoint that is deprecated but still served."""
    headers = {"Deprecation": "true"}
    if sunset_date:
        headers["Sunset"] = sunset_date
    return headers

"""GET /api/v1/version and GET /api/v1/capabilities (EPIC-M3.1).

These are the "representative endpoints" EPIC-M3.1 calls out explicitly for
API version/capability discovery, split out of the combined ``GET
/api/v1/app/bootstrap`` payload (EPIC-M1.132) so a caller that only needs one
concern — a health-check probe polling just the version, or a feature-flag
check — does not have to fetch and parse the whole bootstrap envelope.
Bootstrap remains the one-shot endpoint the Flutter app calls at cold start;
these two read from the same ``api.capabilities``/``api.versioning`` source
of truth so the three endpoints cannot drift apart.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request, Response

from ..capabilities import CAPABILITIES
from ..envelope import success
from ..schemas.bootstrap import ApiCapabilities
from ..schemas.common import SuccessEnvelope
from ..schemas.version import VersionResponse
from ..versioning import API_VERSION, CONTRACT_VERSION

router = APIRouter(tags=["meta"])

# EPIC-M3.13 — API Scope: "Cache headers/ETags where safe". Both bodies
# below are fixed for a process's lifetime (build-time version/capability
# constants, not per-request/DB-derived data), so they are exactly the
# "cacheable, slowly-changing data" EPIC-M3.1's own completion report named
# as the missing precondition for adding this.
_CACHE_CONTROL = "public, max-age=300"


def _etag_for(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f'"{digest[:16]}"'


def _cacheable(request: Request, response: Response, etag: str, body: dict):
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": _CACHE_CONTROL})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return body


@router.get("/version", response_model=SuccessEnvelope[VersionResponse])
def get_version(request: Request, response: Response):
    payload = VersionResponse(apiVersion=API_VERSION, contractVersion=CONTRACT_VERSION)
    etag = _etag_for("version", payload.apiVersion, payload.contractVersion)
    return _cacheable(request, response, etag, success(payload))


@router.get("/capabilities", response_model=SuccessEnvelope[ApiCapabilities])
def get_capabilities(request: Request, response: Response):
    etag = _etag_for("capabilities", CAPABILITIES.model_dump_json())
    return _cacheable(request, response, etag, success(CAPABILITIES))

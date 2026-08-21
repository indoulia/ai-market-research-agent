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

from fastapi import APIRouter

from ..capabilities import CAPABILITIES
from ..envelope import success
from ..schemas.bootstrap import ApiCapabilities
from ..schemas.common import SuccessEnvelope
from ..schemas.version import VersionResponse
from ..versioning import API_VERSION, CONTRACT_VERSION

router = APIRouter(tags=["meta"])


@router.get("/version", response_model=SuccessEnvelope[VersionResponse])
def get_version():
    return success(VersionResponse(apiVersion=API_VERSION, contractVersion=CONTRACT_VERSION))


@router.get("/capabilities", response_model=SuccessEnvelope[ApiCapabilities])
def get_capabilities():
    return success(CAPABILITIES)

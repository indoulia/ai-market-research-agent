"""GET /api/v1/app/bootstrap (EPIC-M1.132).

Tells the Flutter client which contract version it is talking to and which
domain capabilities are currently backed by a real implementation, so the
client can gate UI for capabilities whose API epic (M1.135/137/139/141/145/
147) hasn't landed yet instead of guessing from HTTP 404s.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from ..envelope import success
from ..schemas.bootstrap import ApiCapabilities, BootstrapResponse, ServerTime
from ..schemas.common import SuccessEnvelope
from ..versioning import API_VERSION, CONTRACT_VERSION

router = APIRouter(prefix="/app", tags=["app"])

# Flipped to True as each dependent API epic merges into main.
CAPABILITIES = ApiCapabilities(
    recommendations=True,
    discovery=True,
    marketSummary=True,
    news=True,
    events=True,
    feedback=True,
    preferences=True,
    auth=False,
    analytics=False,
)


@router.get("/bootstrap", response_model=SuccessEnvelope[BootstrapResponse])
def get_bootstrap():
    return success(
        BootstrapResponse(
            apiVersion=API_VERSION,
            contractVersion=CONTRACT_VERSION,
            serverTime=ServerTime(utc=datetime.now(timezone.utc).isoformat()),
            capabilities=CAPABILITIES,
        )
    )

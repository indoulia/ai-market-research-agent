"""Single source of truth for which /api/v1 domain capabilities are backed
by a real implementation (originally EPIC-M1.132's inline constant in
``routers/bootstrap.py``; extracted here in EPIC-M3.1 so ``GET
/api/v1/app/bootstrap`` and the new ``GET /api/v1/capabilities`` cannot drift
apart into two hardcoded lists).
"""

from __future__ import annotations

from .schemas.bootstrap import ApiCapabilities

# Flipped to True as each dependent API epic merges into main.
CAPABILITIES = ApiCapabilities(
    recommendations=True,
    discovery=True,
    marketSummary=True,
    news=True,
    events=True,
    feedback=True,
    preferences=True,
    auth=True,
    analytics=True,
    dashboard=True,
)

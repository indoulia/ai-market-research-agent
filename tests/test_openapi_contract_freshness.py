"""EPIC-M1.144 — Flutter/API integration contract-compatibility gate.

`docs/api/openapi.json` is the Flutter team's typed-client source of truth
(EPIC-M1.132's `docs/api/VERSIONING.md`), generated via
`python scripts/export_openapi.py`. Nothing previously stopped an `api/*`
change from merging without that regeneration step, so the committed
contract could silently drift from what the server actually serves — a
Flutter build against the stale copy would look correct in CI and then
break at runtime. This module makes that drift a CI failure instead
(AC: "Breaking API changes fail CI before UI merge").
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"

# Every path a Flutter repository (`flutter_app/lib/**/*_repository.dart`)
# calls directly. Losing one of these from the live schema is a breaking
# change to the UI even if the contract file were kept in sync, so it is
# asserted independently of the byte-for-byte freshness check below.
FLUTTER_DEPENDENT_PATHS = [
    "/api/v1/app/bootstrap",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/session",
    "/api/v1/auth/logout",
    "/api/v1/me",
    "/api/v1/me/permissions",
    "/api/v1/recommendations",
    "/api/v1/recommendations/{recommendationId}",
    "/api/v1/recommendations/{recommendationId}/history",
    "/api/v1/recommendations/{recommendationId}/events",
    "/api/v1/recommendations/{recommendationId}/outcome",
    "/api/v1/recommendations/{recommendationId}/feedback",
    "/api/v1/preferences",
    "/api/v1/discoveries",
    "/api/v1/market/summary",
    "/api/v1/news",
    "/api/v1/events",
    "/api/v1/tracking/summary",
    "/api/v1/tracking/predictions",
    "/api/v1/tracking/breakdown",
    "/api/v1/tracking/timeseries",
    "/api/v1/system/health",
    "/api/v1/system/providers",
    "/api/v1/system/data-freshness",
    "/api/v1/system/events",
]


def test_committed_openapi_contract_matches_live_schema():
    """Fails if `api/*` changed without `python scripts/export_openapi.py`.

    Compared as parsed JSON (not text) so key ordering/whitespace never
    causes a false failure — only an actual schema difference does.
    """
    live_schema = json.loads(json.dumps(app.openapi()))
    committed = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert live_schema == committed, (
        "docs/api/openapi.json is out of date. Run "
        "`python scripts/export_openapi.py` and commit the result."
    )


def test_flutter_dependent_paths_are_present_in_the_live_schema():
    paths = app.openapi()["paths"]
    missing = [p for p in FLUTTER_DEPENDENT_PATHS if p not in paths]
    assert not missing, f"Flutter-dependent paths missing from the live OpenAPI schema: {missing}"


def test_bootstrap_contract_version_matches_the_flutter_pin():
    """Flutter pins the contract version it was built against
    (`flutter_app/lib/core/app_compatibility.dart::kSupportedContractVersion`)
    and refuses to silently run against an incompatible server
    (AC: "API/UI release compatibility is explicitly versioned"). Keep the
    two constants in this repo in sync explicitly rather than relying on
    someone remembering to update the Dart side by hand.
    """
    from api.versioning import CONTRACT_VERSION

    dart_source = (
        Path(__file__).resolve().parent.parent
        / "flutter_app"
        / "lib"
        / "core"
        / "app_compatibility.dart"
    ).read_text(encoding="utf-8")
    assert f"kSupportedContractVersion = '{CONTRACT_VERSION}'" in dart_source, (
        "api/versioning.py::CONTRACT_VERSION changed without updating "
        "flutter_app/lib/core/app_compatibility.dart::kSupportedContractVersion "
        "to match — the running app would start reporting every launch as "
        "an incompatible-contract build."
    )

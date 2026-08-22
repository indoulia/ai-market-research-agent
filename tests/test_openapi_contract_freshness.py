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
import re
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
    # EPIC-M3.14 — the entries below were added by M3.2/M3.3/M3.4/M3.6/M3.8/
    # M3.9/M3.10 but never appended here, so removing any one of them from
    # the live schema would silently break the Flutter screen that depends
    # on it without failing this gate. See
    # test_flutter_dependent_paths_list_covers_every_repository_call, which
    # derives the same set straight from `flutter_app/lib/**/*_repository.dart`
    # so this list cannot drift silently again.
    "/api/v1/dashboard/snapshot",
    "/api/v1/recommendations/{recommendationId}/timeline",
    "/api/v1/opportunities",
    "/api/v1/discovery/summary",
    "/api/v1/discovery/candidates",
    "/api/v1/discovery/history",
    "/api/v1/learning/summary",
    "/api/v1/learning/history",
    "/api/v1/learning/experiments",
    "/api/v1/feedback/history",
    "/api/v1/predictions/active",
    "/api/v1/predictions/active/{predictionId}",
]

FLUTTER_APP_LIB = Path(__file__).resolve().parent.parent / "flutter_app" / "lib"

# Matches `_client.get('/path')`, `.post('/path/$id', ...)`, etc. across every
# Dart repository file. Interpolated segments (`$id`, `$recommendationId`,
# `$predictionId`) are path parameters, normalized below the same way the
# OpenAPI schema names them (`{recommendationId}` etc.) is not attempted —
# instead we normalize *both* sides to a wildcard so the comparison is
# robust to param-name spelling differences between Dart and the schema.
_DART_CALL_RE = re.compile(r"\.(?:get|post|put|delete|patch)\('(/[^']+)'")
_PATH_PARAM_RE = re.compile(r"\$\{?\w+\}?")


def _normalize(path: str) -> str:
    """Collapses any path-parameter segment (Dart `$id` or OpenAPI
    `{recommendationId}`) to a single `*` wildcard for comparison."""
    path = _PATH_PARAM_RE.sub("*", path)
    path = re.sub(r"\{[^}]+\}", "*", path)
    return path


def _flutter_called_paths() -> set[str]:
    """Every `/api/v1/*` path a Flutter repository calls directly, derived
    from source rather than hand-maintained, so this can never itself go
    stale the way `FLUTTER_DEPENDENT_PATHS` silently did."""
    called: set[str] = set()
    for dart_file in FLUTTER_APP_LIB.rglob("*.dart"):
        text = dart_file.read_text(encoding="utf-8")
        for match in _DART_CALL_RE.finditer(text):
            called.add("/api/v1" + _normalize(match.group(1)))
    return called


def test_flutter_dependent_paths_list_covers_every_repository_call():
    """EPIC-M3.14 — guards against the exact drift this module already had:
    `FLUTTER_DEPENDENT_PATHS` is hand-maintained and fell behind as M3.2
    onward added `/dashboard/snapshot`, `/opportunities`, `/discovery/*`,
    `/learning/*`, `/feedback/history` and `/predictions/active*` without
    anyone re-adding them here. Scans the real Dart source for every call
    site instead of trusting the list to have kept up with it.
    """
    called = _flutter_called_paths()
    declared = {_normalize(p) for p in FLUTTER_DEPENDENT_PATHS}
    missing = sorted(called - declared)
    assert not missing, (
        "Flutter calls these API paths but FLUTTER_DEPENDENT_PATHS doesn't "
        f"list them (so losing one from the schema wouldn't fail CI): {missing}"
    )


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

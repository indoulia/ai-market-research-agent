# EPIC-M3.1 — MRA Application Platform Foundation

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Establish the production-quality Flutter application foundation and API/BFF boundary for a responsive MRA client running on mobile and web.

## UI Scope
- Flutter application structure with feature-based modules.
- Material 3 foundation with a restrained professional visual language.
- Typography, spacing, elevation, iconography, semantic states and sizing tokens.
- Responsive breakpoints based on available window size, not device labels.
- Light/dark theme architecture if supported by existing product requirements.
- Desktop/web, tablet and mobile layouts.
- Central navigation, routing, error boundary and loading-state conventions.
- Typed API client generation/adapter boundary.
- Avoid business logic and provider logic inside widgets.

## API Contract
Base: `/api/v1`

Required foundation behavior:
- Versioned API envelope/error contract.
- Correlation/request ID.
- Authentication/session context.
- Consistent pagination/filter/sort conventions.
- RFC-style validation/error representation.
- Health/readiness endpoint.
- API capability/version discovery.

Representative endpoints:
- `GET /api/v1/health`
- `GET /api/v1/version`
- `GET /api/v1/capabilities`

## Acceptance Criteria
- Flutter app starts cleanly on supported mobile and web targets.
- Responsive layout adapts without device-specific branching.
- API contracts are versioned and machine-readable.
- UI and API use typed DTOs/contracts rather than ad-hoc JSON assumptions.
- Global loading, error, empty and retry states are standardized.
- No screen embeds backend/provider implementation details.

## Completion Report (2026-08-22)

**Context:** see `docs/epics/EPIC-M3-ROADMAP-NOTE.md`. This EPIC's number
was renumbered from a collision (was `M1.132` in the newer combined
roadmap) with the older, already-implemented split track that also owns a
`M1.132` (API Contract & BFF Foundation, `DONE`/merged PR #147),
`M1.133` (Flutter Design System, `DONE`) and `M1.134` (Flutter App Shell &
Responsive Navigation, `DONE`). That split track already shipped almost
everything this EPIC's UI Scope and API Contract sections ask for. This
session's job was to diff M3.1's acceptance criteria against that existing,
merged code, not to build a second, parallel Flutter app or API.

**Already satisfied by existing M1.132/M1.133/M1.134 (+ later M1.13x)
work — verified, not reimplemented:**
- Flutter feature-based module structure — `flutter_app/lib/{app_shell,core,design_system,features}/*`, one directory per domain (`dashboard`, `discover`, `detail`, `market`, `news_events`, `preferences`, `feedback`, `tracking`, `auth`).
- Material 3 foundation, restrained visual language, typography/spacing/elevation/semantic-state color tokens — `flutter_app/lib/design_system/theme/mra_theme.dart`, `tokens/mra_colors.dart` (explicit `warning`/`error`/positive/market-state semantic colors, light+dark variants), `tokens/mra_spacing.dart`, `tokens/mra_typography.dart`.
- Light/dark theme architecture — `MraTheme.light()`/`MraTheme.dark()`, wired in `flutter_app/lib/main.dart` via `MaterialApp.router(theme:, darkTheme:)`.
- Responsive breakpoints by available width, not device labels, plus desktop/tablet/mobile layouts — `flutter_app/lib/app_shell/app_shell_scaffold.dart` (nav rail vs. bottom nav by `MediaQuery` width) and per-screen `LayoutBuilder` usage (e.g. `dashboard_screen.dart`, `discover_screen.dart`).
- Central navigation/routing — `flutter_app/lib/app_shell/app_router.dart` (`go_router` `StatefulShellRoute`, one branch per destination, auth-gated redirect logic from EPIC-M1.146).
- Global loading/error/empty/retry state conventions — `flutter_app/lib/design_system/components/state_views.dart` (`MraStateView.empty/.error/.offline`, each with an optional retry `actionLabel`/`onAction`) and `skeleton_loader.dart` for loading, used consistently across `dashboard`, `discover`, `market`, `tracking`, `preferences`, `news_events` screens (verified by `flutter test`, incl. `tracking_screen_test.dart`'s explicit "shows an error state and retries on demand" / "shows an empty state" cases).
- Typed API client boundary — `flutter_app/lib/core/api_client.dart` (`ApiClient.get/put/post` decode the canonical envelope into `ApiResponse{data, meta}`; screens/repositories never parse raw `http.Response` JSON themselves) plus `api_exception.dart` for typed error mapping.
- No business/provider logic in widgets — repositories/controllers live under `core/` and per-feature `*_repository.dart`/controller files, separate from `*_screen.dart` widget files (existing pattern, unchanged).
- Versioned API envelope/error contract, correlation/request ID, pagination/sort conventions, RFC-style validation errors, health endpoint — `api/envelope.py`, `api/request_context.py`, `api/pagination.py`, `api/exception_handlers.py`, `api/routers/health.py` (`GET /api/v1/health`), all from EPIC-M1.132, unchanged.
- Authentication/session context integration point — `api/deps.py` (`get_optional_bearer_subject`/`require_bearer_subject`), enforced for real by EPIC-M1.145's auth router (`api/routers/auth.py`), already merged.

**Genuine gap found and implemented this session:** EPIC-M1.132 shipped
`GET /api/v1/health` and a combined `GET /api/v1/app/bootstrap` (version +
capabilities together), but M3.1 explicitly calls out `GET /api/v1/version`
and `GET /api/v1/capabilities` as their own representative discovery
endpoints, and neither existed as standalone routes. Added, following the
existing `api/` package conventions exactly:
- `api/capabilities.py` — the `CAPABILITIES` constant, extracted out of
  `api/routers/bootstrap.py` (which previously defined it inline) so
  `/app/bootstrap` and the new `/capabilities` endpoint read from one
  source of truth instead of two hardcoded lists that could drift apart.
- `api/schemas/version.py` — `VersionResponse(apiVersion, contractVersion)` DTO.
- `api/routers/meta.py` — `GET /api/v1/version` and `GET /api/v1/capabilities`, both wrapped in the canonical `SuccessEnvelope`, wired into `api/app.py`'s `api_router`.
- `api/routers/bootstrap.py` updated to import `CAPABILITIES` from `api/capabilities.py` instead of redefining it.
- `docs/api/openapi.json` regenerated (`python scripts/export_openapi.py`) so the two new paths are in the committed contract artifact.

**Tests (TDD):** added to `tests/test_api_contract.py`:
- `test_version_endpoint_reports_api_and_contract_version` — asserts `GET /api/v1/version` returns `apiVersion == "v1"` and a non-empty `contractVersion`.
- `test_capabilities_endpoint_matches_bootstrap_capabilities` — asserts `GET /api/v1/capabilities` returns the same object as `bootstrap.capabilities`, and matches the expected all-`true` capability set.

**Validation run:**
```
python -m pytest tests/test_api_contract.py -q
# 15 passed in 4.53s   (13 pre-existing + 2 new)

python -m pytest -q
# 1327 passed, 9 skipped in 149.69s — full existing suite, no regressions

cd flutter_app && flutter pub get && flutter test
# All tests passed! (114 tests, incl. widget_test.dart's
# "App boots into the Home destination of the app shell")
```

**Deliberately not done (rationale):**
- No second Flutter app or second API surface was created — would fork the product into two incompatible UIs, explicitly out of scope per this EPIC's actual intent.
- No Flutter-side consumer of the new `/version`/`/capabilities` endpoints was added: the app already gets both pieces of data from the one `GET /api/v1/app/bootstrap` call it makes at cold start (EPIC-M1.146's splash flow); the new endpoints exist for external/tooling callers that want just one concern (e.g. a monitoring probe), per the EPIC's own framing of them as "representative endpoints" for API discovery, not as a mandate to change how the app itself bootstraps.
- ETag/Last-Modified caching remains deferred (unchanged from EPIC-M1.132's own explicit deferral) — still no endpoint with cacheable, slowly-changing data that needs it.

**Conclusion:** EPIC-M3.1's scope was ~95% already satisfied by the
existing, merged M1.132/M1.133/M1.134 (+ M1.141/M1.145/M1.146) work. The
one concrete, explicitly-named gap (`GET /api/v1/version` and
`GET /api/v1/capabilities` as standalone endpoints) has been implemented,
tested and verified above. Marking this EPIC `DONE`.

# EPIC-M1.144 — Flutter/API Integration & End-to-End Contract Validation

**Track:** CROSS-TRACK
**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Prove that the Flutter application and MRA APIs operate as one coherent product with no contract drift, inconsistent state handling or platform-specific behavior.

## Scope
- Generate/use typed Flutter API client from M1.132 OpenAPI contract.
- Replace fixtures with live API responses behind environment configuration.
- Contract compatibility tests in CI.
- API mock server/fixtures for UI development.
- End-to-end flows: launch → recommendations → detail → history → event → feedback → preferences.
- Error states: unauthorized, rate limited, timeout, stale data, provider unavailable, server error, empty result.
- Offline/reconnect behavior where supported.
- Deep-link tests on web.
- Responsive tests at representative widths rather than device-specific assumptions.
- Verify exact target/SL/trust/confidence values shown in UI match API payloads.

## Acceptance Criteria
- Breaking API changes fail CI before UI merge.
- UI never silently falls back to stale fixture data in production builds.
- Every primary user journey has an automated happy-path and failure-path test.
- Web deep links work after reload.
- Mobile and web render the same domain truth with adaptive presentation.
- API/UI release compatibility is explicitly versioned.

## Parallelization
Cross-track integration. API and UI teams can work independently until contract integration begins.

## Dependencies
M1.132, M1.133, M1.134, M1.135, M1.136, M1.137, M1.138, M1.139, M1.140, M1.141, M1.142, M1.143.

## Completion Report

### What was already true before this EPIC

The M1.132–M1.143 dependency chain had already delivered most of the
"one coherent product" plumbing: `flutter_app/lib/core/api_client.dart`
talks to the real `/api/v1` contract (no fixtures anywhere in `lib/`),
`ApiConfig.baseUrl` is overridable via `--dart-define=API_BASE_URL`, every
repository is a thin boundary over one real endpoint, and per-screen
widget tests already cover most individual success/loading/empty/error
states. What was missing was the *cross-track* proof this EPIC is
actually about: a contract-drift gate, a true full-app journey test (not
screen-isolated fakes), an API/UI version-compatibility check, a stale-
data indicator that the UI silently dropped, a dev-only mock server, and
an explicit deep-link-survives-reload test.

### What was implemented

**Contract-compatibility gate in CI** (`tests/test_openapi_contract_freshness.py`):
- `test_committed_openapi_contract_matches_live_schema` fails if `api/*`
  changes without re-running `python scripts/export_openapi.py` — this
  caught real, pre-existing drift: `docs/api/openapi.json` was missing
  `maxLength`/`maxItems` constraints already enforced live on
  `preferences`/`feedback` fields. Regenerated and committed as part of
  this PR.
- `test_flutter_dependent_paths_are_present_in_the_live_schema` asserts
  every path a Flutter repository calls still exists in the live schema.
- `test_bootstrap_contract_version_matches_the_flutter_pin` keeps
  `api/versioning.py::CONTRACT_VERSION` and
  `flutter_app/lib/core/app_compatibility.dart::kSupportedContractVersion`
  from silently diverging.
- Runs as part of the existing `pytest -q` step in `.github/workflows/test.yml` — no new workflow needed.

**API/UI release-compatibility check** (`core/app_compatibility.dart`,
`core/app_bootstrap_repository.dart`, `app_shell/contract_incompatible_screen.dart`,
wired into `main.dart::MraApp`):
- On launch, `MraApp` calls `GET /app/bootstrap` and compares the
  server's `contractVersion` against the build's pinned
  `kSupportedContractVersion`. A confirmed mismatch replaces the whole
  app with a blocking "Update required" screen — never a silent guess at
  field shapes.
- A failed/slow bootstrap call (offline, server down) is treated as
  non-fatal — launch proceeds normally. Compatibility is enforced only on
  a *confirmed* mismatch, never merely because the check didn't answer
  (Scope: "Offline/reconnect behavior where supported").

**True end-to-end journey tests** (`flutter_app/test/e2e/end_to_end_journey_test.dart`):
- Added `ApiClient.debugHttpClientOverride` (mirrors the existing
  `bearerToken`/`onSessionExpired` "wire it centrally" static seam) so a
  test can redirect every default, un-injected `ApiClient()` — i.e. the
  real app exactly as `main.dart` builds it — at one scripted HTTP
  transport, without threading a fake repository through every
  screen/route.
- Happy path: sign-in → recommendations → detail (history+event fetched
  together) → feedback → preferences, driven through the real
  `buildAppRouter`, real screens, real repositories. Target/stop-loss/
  confidence/trust values are asserted via `find.bySemanticsLabel`
  against the exact payload strings (e.g. `"Target 176.50"`,
  `"Confidence 71 out of 100"`) — proving the AC "exact target/SL/trust/
  confidence values shown in UI match API payloads", not a reformatted
  guess.
- Failure paths at the same full-stack level: unauthorized/session-expired
  (redirects to sign-in, not a stale screen), rate-limited (429, retryable
  error banner), server error (500 on detail), empty recommendations
  result, and a transport-level network failure (thrown exception ->
  `MRA_NETWORK`).
- `flutter_app/test/widget_test.dart` gained a compatibility-gate test;
  `flutter_app/test/app_shell/app_router_auth_test.dart` gained a deep-link
  test that cold-starts a fresh `GoRouter` at
  `/home/recommendation/99` (simulating a real reload, not in-app
  navigation) and asserts it resolves straight to that exact nested
  route/screen.

**Stale-data indicator** (`design_system/components/recommendation_card.dart`,
`features/dashboard/dashboard_screen.dart`): the API's `evidenceFreshness`
field (`FRESH`/`STALE`/`UNKNOWN`) was parsed by `Recommendation.fromJson`
but never rendered anywhere — a real gap against the Scope's "stale data"
error state. Added an optional `evidenceFreshness` to
`RecommendationCardData` and a "Stale evidence" warning chip shown only
when `STALE`, wired from the dashboard. Covered by two new
`dashboard_screen_test.dart` cases.

**API mock server for UI development** (`flutter_app/tool/mock_api_server.dart`):
a real, standalone `dart:io` HTTP server covering bootstrap/auth/
recommendations/detail/history/events/outcome/feedback/preferences,
using the same envelope/error/field shapes as the real API. Run with
`dart run tool/mock_api_server.dart` and point the app at it with
`--dart-define=API_BASE_URL=http://localhost:8090`. It lives in `tool/`
(never imported by `lib/`), so it cannot end up in a shipped build — the
app only ever calls the real API in production regardless of this tool
existing. Manually smoke-tested against bootstrap/recommendations/
preferences-PUT/unknown-route during this implementation.

### How it was tested

- `DATABASE_URL="sqlite:///:memory:" PYTHONPATH=. python -m pytest -q` →
  **1328 passed, 9 skipped** (full existing backend suite, no regressions;
  includes the 3 new contract-freshness tests).
- `flutter analyze` → **No issues found.**
- `dart format --output=none --set-exit-if-changed lib test` → clean.
- `flutter test` (full suite) → **127 passed**, including the new
  `test/e2e/end_to_end_journey_test.dart` (6 tests), the extended
  `app_router_auth_test.dart` and `dashboard_screen_test.dart`, and the
  new `core/app_bootstrap_repository_test.dart` /
  `core/app_compatibility_test.dart`.
- Manually ran `dart run tool/mock_api_server.dart 8091` and curled
  `/app/bootstrap`, `/recommendations`, `PUT /preferences`, and an unknown
  route to confirm the envelope/error shapes and stateful preference
  round-trip.

### Scope deliberately deferred (not silently skipped)

- **Full OpenAPI-codegen typed client.** The existing hand-written
  `ApiClient` + per-feature repositories (established by M1.136+) already
  give every field a typed Dart model with no fixture fallback; adding a
  generated-client toolchain on top would duplicate that without a
  concrete gap it closes. The new contract-freshness test gives the same
  drift protection a generated client's build step would.
- **Deep-link web tests running in an actual browser.** Flutter web here
  uses the default hash URL strategy (no `usePathUrlStrategy()` call) and
  `flutter_app/nginx.conf` already has an SPA `try_files` fallback, so a
  reload is safe by construction — verified via a `flutter_test`-level
  cold-start-at-a-nested-route test rather than a browser/integration_test
  run, which this repo's toolchain doesn't otherwise use anywhere.
- **Persistent offline data cache.** "Offline/reconnect" is handled by
  fail-open bootstrap compatibility plus each screen's existing
  retry/pull-to-refresh; a real offline cache (e.g. persisting the last
  successful fetch for a fully airplane-mode cold start) is a larger,
  separate feature not implied by this EPIC's named journey/error-state
  list.
- **`provider unavailable`** is exercised as a transport-level failure
  (thrown exception -> `MRA_NETWORK`) in the e2e suite rather than as a
  distinct `MRA_*` error code, because the backend does not define one —
  inventing a code ad hoc would violate `docs/api/VERSIONING.md`'s "new
  codes are added in `api/errors.py`, never invented ad hoc" rule.

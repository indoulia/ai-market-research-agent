# EPIC-162 — System & Provider Health

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Provide a compact operational view of MRA data/provider health, freshness, latency and fallback state so users can distinguish a market condition from an information-system degradation.

## UI Scope
- Provider status grid.
- Data freshness by capability.
- Last successful fetch.
- Latency indicator.
- Degraded/fallback state.
- Provider quality/cost summary where appropriate.
- Market-calendar/session status.
- System incident/history drill-down.

## API Contract
`GET /api/v1/system/health`
`GET /api/v1/system/providers`
`GET /api/v1/system/data-freshness`
`GET /api/v1/system/events`

Provider response:
`providerId`, `capability`, `status`, `lastSuccessAt`, `latencyMs`, `freshness`, `failureRate`, `fallbackActive`, `qualityScore`.

## Acceptance Criteria
- Health state is read-only to normal users.
- Provider outages and stale data are visible.
- UI never exposes secrets or provider credentials.
- Health information reconciles with EPIC-093, EPIC-121 and EPIC-129.

## Completion Report (2026-08-22)

**Context:** see `docs/epics/EPIC-M3-ROADMAP-NOTE.md`. There is no older
split-track `EPIC-145` equivalent for *this* product surface (the old
`EPIC-145` is "Feedback/Preferences UI", unrelated) — unlike most sibling
M3.x EPICs, this one's API contract (`/api/v1/system/*`) genuinely did
not exist anywhere before this session. What *did* already exist,
extensive and unduplicated by this session, was the backend reliability/
freshness machinery this EPIC's own AC says the UI must "reconcile
with":

**Already satisfied by existing, merged work — composed, not
reimplemented:**
- Per-`(data_type, provider_id)` reliability, verdicts (`OK`/`WEAK`/
  `INSUFFICIENT_SAMPLE`) and zero-cost accounting — `app/provider_quality.py`
  (EPIC-093), `compute_provider_quality_report`.
- Outage-severity history (`NONE`/`PARTIAL`/`TOTAL`) naming exactly which
  provider ids are degraded, per data type — `app/provider_outage_tracker.py`
  (EPIC-114), `record_outage_snapshot`/`get_latest_outage_snapshot`.
- Freshness policy per data type (`FRESHNESS_POLICY`) and the immutable
  `DataFetchAttempt` log every metric above is computed from —
  `app/refresh_policy.py` (EPIC-030/EPIC-093).
- Ingestion-latency degradation history — `app/information_latency.py`
  (EPIC-129), `LatencyDegradationReport`.
- Unexpected market closures — `app/market_calendar.py` (EPIC-124),
  `MarketUnexpectedClosure`.
- NSE weekday/session-window classification with no DB dependency —
  `app/schedule_orchestration.py::classify_session` (EPIC-121); no
  `MarketCalendarVersion` is seeded anywhere in this platform's
  production data, the same honest gap `api/services/market.py::
  get_market_summary` already documents for `marketStatus` — reusing
  `classify_session` directly is still strictly more informative than a
  permanent `UNKNOWN`.
- The `/api/v1` envelope/pagination/router conventions themselves
  (EPIC-135), unchanged.

**Genuinely new work this session (the actual gap — the four named
endpoints did not exist under any name):**
- `api/schemas/system.py` — `Freshness`, `ProviderStatus`,
  `SystemHealthResponse`, `DataFreshnessItem`, `SystemEventItem` DTOs.
  `capability` is realized as the real `data_type` string
  (`MARKET_DATA`/`NEWS_EVENT`/`FUNDAMENTAL_DATA`) that `DataFetchAttempt`/
  `ProviderQualityMetric` already segment by — not a separate, unused
  `provider_contracts.ALL_CAPABILITIES` vocabulary no fetch-attempt row
  actually carries. `qualityScore` is EPIC-093's own `success_rate`;
  `failureRate` is `1 - success_rate`.
- `api/services/system_health.py`:
  - `get_provider_status` — per-provider grid row: EPIC-093's verdict/
    quality-score/cost report, plus this module's own new
    per-`(data_type, provider_id)` last-successful-fetch and average-
    ingestion-latency lookup (the two fields EPIC-093's report doesn't
    carry), plus `fallbackActive` from EPIC-114's latest outage snapshot
    for that data type.
  - `get_data_freshness` — last successful fetch and staleness per
    capability against `FRESHNESS_POLICY`.
  - `get_system_health` — overall `OK`/`DEGRADED`/`OUTAGE` rollup: a DB
    connectivity check (same `SELECT 1` EPIC-135's `/health` already
    does), whether any latest outage snapshot is `TOTAL` (→ `OUTAGE`) or
    `PARTIAL`/any provider is `WEAK` (→ `DEGRADED`), plus
    `classify_session`'s market-session label.
  - `get_system_events` — merges EPIC-114's outage-severity history
    (excluding `NONE`), EPIC-124's unexpected-closure log and EPIC-129's
    `DEGRADED`-verdict latency reports into one time-ordered incident
    feed, offset-cursor paginated (per `api/pagination.py`'s own
    guidance: appropriate here since every source is a periodic/
    administrative snapshot log, not a high-volume live stream).
  - Live provider health pings are honestly out of scope: no
    credentialed provider registry is wired into the API process, so
    `compute_provider_quality_report` is always called with no live
    `providers` — `status` reflects only the historical
    `DataFetchAttempt` verdict, the same posture EPIC-093's own docstring
    documents for callers that "only want historical metrics". No
    provider credential/config is ever serialized by this API surface,
    satisfying "UI never exposes secrets or provider credentials"
    structurally.
- `api/routers/system.py` — `GET /system/{health,providers,
  data-freshness,events}`, all public/unauthenticated GETs (no route
  accepts a body or mutates state), matching the AC "read-only to normal
  users" and this repo's own convention for other public informational
  endpoints (`/market/summary`, `/dashboard/snapshot`, `/tracking/*` all
  likewise require no auth). Wired into `api/app.py`.
- `docs/api/openapi.json` regenerated; `tests/
  test_openapi_contract_freshness.py::FLUTTER_DEPENDENT_PATHS` extended
  with the four new paths since the Flutter app now consumes them.
- Flutter: a fourth "System" tab on the existing Settings destination
  (`flutter_app/lib/features/preferences/preferences_settings_screen.dart`)
  — an operational, read-only concern belongs alongside Preferences/
  Settings/History, not a seventh primary nav destination (EPIC-137's
  shell has a fixed six). `flutter_app/lib/features/system/`:
  `provider_status.dart`, `data_freshness_item.dart`,
  `system_health_summary.dart`, `system_event.dart`,
  `system_repository.dart`, `system_health_screen.dart`. The screen
  shows an overall status/market-session/database banner, an
  `MraDenseTable` provider grid (provider, capability, status chip,
  last success, latency, freshness chip, fallback badge, quality %), a
  per-capability freshness list, and a paginated incident-history
  timeline ("Load more", mirroring EPIC-161's `FeedbackHistoryScreen`
  pattern) — covering every UI Scope bullet except "provider quality/
  cost summary" (deferred, see below).

**Tests (TDD):**
- `tests/test_api_system_health.py` (9 tests) — reliable/weak/
  insufficient-sample provider verdicts, `fallbackActive` reflecting the
  latest outage snapshot, per-capability freshness (including "no data
  yet"), `OK`/`DEGRADED`/`OUTAGE` health rollup logic, and events
  merging/pagination/ordering (newest first) across all three incident
  sources.
- `flutter_app/test/features/system/system_health_screen_test.dart` (5
  tests) — status/session rendering, provider grid + freshness list
  rendering, events pagination "Load more", and the error/retry state.
- `flutter_app/test/features/preferences/preferences_settings_screen_test.dart`
  — one new case: switching to the "System" tab renders the new screen.

**Validation run:**
```
python -m pytest tests/test_api_system_health.py tests/test_openapi_contract_freshness.py -q
# 12 passed

python -m pytest -q
# 1444 passed, 9 skipped in 147.13s — full existing suite, no regressions

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# Formatted 138 files (0 changed)

cd flutter_app && flutter test
# 177 tests, All tests passed!
```

**Deliberately deferred (rationale):**
- "Provider quality/cost summary" as its own dedicated widget: every
  provider adapter in this codebase is free
  (`app/provider_quality.py::PROVIDER_COST_PER_REQUEST_USD` is `0` for
  all six), so a dedicated cost-summary UI would only ever render
  "$0.00" for every provider — decorative, not informative, until a paid
  provider is actually added. `qualityScore` (success rate) is shown per
  provider in the grid, which is the genuinely-populated half of that
  bullet.
- No live provider health ping / no credentialed provider registry in
  the API process — the same explicit, honest gap EPIC-093 itself
  documents; this surface reports historical `DataFetchAttempt`-derived
  status only, never a live vendor call.
- No write/acknowledge/mute action on an incident (this EPIC's API
  Contract lists only the four `GET` routes; adding a mutation would be
  scope creep beyond "read-only to normal users").

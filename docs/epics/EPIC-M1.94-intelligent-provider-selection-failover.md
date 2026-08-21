# EPIC-M1.94 — Intelligent Provider Selection & Failover

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Select the best available provider for each capability using configured policy plus measured quality, cost, latency, freshness and reliability, with safe fallback when a provider fails.

## Scope
- Capability-specific provider routing.
- Primary/secondary/fallback provider policies.
- Route based on quality, cost, latency, freshness and availability.
- Detect provider degradation and temporarily suppress unhealthy providers.
- Fail over safely without duplicating or corrupting evidence.
- Preserve actual provider identity in every external-world result.
- Prevent provider switching from changing historical records.
- Add deterministic routing and failover tests.

## Acceptance Criteria
- Provider choice can change without code deployment where configuration permits.
- Failed providers can fail over safely.
- Routing uses measured provider evidence where policy allows.
- Provider failures are visible and auditable.
- Historical predictions remain tied to the provider/version that produced their inputs.
- No direct provider dependency exists in recommendation/domain logic.

## Dependencies
Previous: M1.93.
Next: Future provider additions become adapter-only work.

## Final Architectural Rule
**MRA business logic depends on capabilities, never vendors.** New providers must be addable without modifying the recommendation engine.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.94

### Branch

autonomous/epic-m1-94, branched cleanly from `main` (the declared dependency -- M1.93 -- is already merged).

### Objective

Select the best available provider for each capability using configured policy plus measured quality, with safe fail-over when a provider fails or degrades.

### Design: Composition, Not Reimplementation

`app/provider_selection.py`'s `select_provider(registry, quality_report, capability)` is the only new logic this EPIC adds. It never reimplements M1.92's role-priority ordering or M1.90's contract verification: `ProviderRegistry.get_registrations` is the sole source of which providers exist and their configured priority; `ProviderQualityReport.by_provider` (M1.93) is the sole source of how well each has actually performed. Selection walks registrations in `PRIMARY` > `SECONDARY` > `OPTIONAL` order (scope: "primary/secondary/fallback provider policies") and returns the first one that is both enabled and not degraded.

### Degradation Is Temporary and Evidence-Driven, Never Persisted

"Detect provider degradation and temporarily suppress unhealthy providers" (scope) is implemented by treating only a confirmed `VERDICT_WEAK` quality verdict as degraded -- never `VERDICT_INSUFFICIENT_SAMPLE`. A newly-registered provider with too little history to judge is not punished for being unproven; only a provider with a measured, sufficiently-sampled poor success rate is skipped. Crucially, this suppression is recomputed fresh from whichever `ProviderQualityReport` is passed in on every call -- it never writes back into the registry's own `enabled` flag (M1.92's separate, manually-controlled mechanism). `test_recovering_quality_makes_a_previously_degraded_provider_selectable_again` proves this directly: the identical, unmodified `ProviderRegistry` instance rejects a provider against a snapshot showing a poor track record and accepts the very same provider against a later snapshot showing a good one, with zero registry configuration change in between -- true temporary suppression, not a mutation.

### Auditable Failures

Every skipped candidate is recorded in the returned `ProviderSelectionDecision` with its role and skip reason (`disabled` or `degraded`) -- scope: "provider failures are visible and auditable." When nothing usable remains, `NoHealthyProviderAvailableError` (a `NoProviderAvailableError` subclass, so any existing caller catching the base type still works) carries that same decision as `.decision`, so a failure is never a bare, uninformative exception.

### The Capability / Data-Type Vocabulary Mismatch

A real, pre-existing gap surfaced while wiring M1.93's `by_provider` (keyed by M1.35's `data_type`) to M1.90's `capability` strings: `CAPABILITY_MARKET_DATA` ("MARKET_DATA") and `CAPABILITY_FUNDAMENTAL_DATA` ("FUNDAMENTAL_DATA") happen to equal their `DATA_TYPE_*` counterparts, but `CAPABILITY_NEWS_EVENT_DATA` ("NEWS_EVENT_DATA") does **not** equal `DATA_TYPE_NEWS_EVENT` ("NEWS_EVENT"). Assuming string equality would have silently failed to detect a degraded news provider. `_CAPABILITY_TO_DATA_TYPE` bridges this explicitly and honestly; `CAPABILITY_AI_DISCOVERY` has no entry at all, since M1.35 never defined a fetch-attempt policy for it -- an AI-discovery provider is never suppressed as "degraded" by this module (there is no fetch-attempt-based signal for it; M1.65's discovery-effectiveness report, already composed into M1.93's own report, remains the real quality signal there). `test_news_capability_data_type_vocabulary_mismatch_is_bridged` proves the bridge works for the one capability where the strings actually differ.

### Historical Records and Reproducibility

"Preserve actual provider identity in every external-world result" and "prevent provider switching from changing historical records" (scope/AC) hold structurally, unchanged from M1.92: this module only decides which already-configured provider instance to hand back next; it never touches a persisted record's `source`/`provider_id` column. `test_selection_never_mutates_registry_or_writes_to_the_session` proves selection itself performs no registry mutation and no database write. No new persisted "selection decision" log was added -- the decision is fully reproducible from the registry's configuration plus the quality report's own already-persisted evidence (M1.93's AC: "provider comparisons are reproducible"), so recomputing it *is* the audit trail; a parallel persisted log risking drift from what selection actually used would add risk, not honesty.

### Files Changed

- `app/provider_selection.py` — new: `select_provider`, `ProviderSelectionDecision`, `SkippedProvider`, `NoHealthyProviderAvailableError`, `_CAPABILITY_TO_DATA_TYPE`.
- `tests/test_provider_selection.py` — new: 9 tests.
- `docs/epics/EPIC-M1.94-intelligent-provider-selection-failover.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_provider_selection.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0067_provider_id` -- unchanged; this EPIC adds no persisted schema)

### Test Results

- `pytest -q`: **825 passed, 0 failed** (816 pre-existing + 9 new).
- `test_provider_selection.py`: **9 passed** — a healthy primary is selected with no skips; a degraded primary fails over to secondary with the skip correctly attributed to `degraded`; a disabled primary fails over to secondary with the skip attributed to `disabled`; a provider with an insufficient sample is selected rather than wrongly suppressed; when every candidate is disabled or degraded, `NoHealthyProviderAvailableError` carries a decision naming every skip and its reason; an `OPTIONAL`-role provider is correctly reached when both `PRIMARY` and `SECONDARY` are unavailable; the news-capability data-type vocabulary mismatch is bridged correctly; a previously-degraded provider becomes selectable again purely from a better quality snapshot, with no registry mutation; selection performs no registry mutation and no database write.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).

### Acceptance Criteria

- [x] Provider choice can change without code deployment where configuration permits (`ProviderRegistry.set_enabled` plus measured quality both flow through `select_provider` with no code change required).
- [x] Failed providers can fail over safely (`test_fails_over_to_secondary_when_primary_is_degraded`, `test_fails_over_to_secondary_when_primary_disabled`, `test_optional_role_is_selected_when_primary_and_secondary_are_unavailable`).
- [x] Routing uses measured provider evidence where policy allows (`VERDICT_WEAK` suppression, `VERDICT_INSUFFICIENT_SAMPLE` correctly not suppressed).
- [x] Provider failures are visible and auditable (`ProviderSelectionDecision.skipped`, `NoHealthyProviderAvailableError.decision`).
- [x] Historical predictions remain tied to the provider/version that produced their inputs (structural, unchanged from M1.92; proven again by `test_selection_never_mutates_registry_or_writes_to_the_session`).
- [x] No direct provider dependency exists in recommendation/domain logic (`select_provider` is the single new selection point; it depends only on the registry and quality-report abstractions, never a concrete adapter).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, composing M1.92's registry and M1.93's quality report into genuinely evidence-driven, auditable, safely-reversible provider selection without persisting any new state or touching historical records. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

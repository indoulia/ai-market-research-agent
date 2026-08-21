# EPIC-M1.114 — Provider Outage Resilience & Data Continuity

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Prevent provider outages, rate limits or degraded responses from silently producing stale or unreliable predictions.

## Scope
- Detect provider health degradation.
- Fail over through M1.94 provider routing.
- Track partial data availability explicitly.
- Prevent stale provider data from being treated as current.
- Preserve outage/fallback provenance.
- Suppress affected predictions when minimum evidence policy is not satisfied.
- Recover automatically when providers return to healthy state.

## Dependencies
M1.90, M1.94, M1.101, M1.105.

## Completion Report

**Status:** DONE — merged to main via PR #207 (`eff89cd`).

**Implementation:**
- `app/provider_outage_tracker.py`: a new, versioned (`OUTAGE_SNAPSHOT_VERSION = "POT-001"`) module.
- **Detect provider health degradation / fail over through M1.94 provider routing / recover automatically when providers return to healthy state:** already hold unchanged via M1.94's own `select_provider`, which recomputes fresh from M1.93 on every call and recovers with no configuration change — not duplicated here.
- **Track partial data availability explicitly:** `record_outage_snapshot` classifies a data type's severity as `NONE`/`PARTIAL`/`TOTAL` by reusing M1.93's own `ProviderQualityMetric.verdict` unchanged — a provider with `VERDICT_INSUFFICIENT_SAMPLE` or no metric at all is honestly counted as healthy, not degraded, the same "insufficient sample is not the same as unreliable" posture M1.94's own selection logic already established (verified by `test_insufficient_sample_not_treated_as_degraded` and `test_provider_with_no_metric_at_all_treated_as_healthy`).
- **Preserve outage/fallback provenance:** every snapshot immutably names exactly which provider ids were degraded (`degraded_provider_ids`).
- **Prevent stale provider data from being treated as current / suppress affected predictions when minimum evidence policy is not satisfied:** already covered by M1.35's freshness checks, M1.74's evidence-quality gate, and M1.112's assumption-decay tracker — not duplicated; this module's own signal is a read-only input a future revision of those could compose, with no write path to `Prediction` or any recommendation-facing table.
- New immutable table `provider_outage_snapshots` (migration `0091_provider_outage_resilience.py`), idempotent by `(data_type, evaluated_at)`.

**Tests:** `tests/test_provider_outage_tracker.py` (7 tests) — `NONE`/`PARTIAL`/`TOTAL` severity classification, insufficient-sample and no-metric-at-all correctly treated as healthy, idempotency and history accumulation, empty-history lookup.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_provider_outage_tracker.py -q` → `7 passed`
- `python -m pytest -q` (full suite) → `1116 passed`
- `python -m alembic heads` → single head `0091_provider_outage (head)`, chain resolves cleanly

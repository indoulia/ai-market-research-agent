# EPIC-019 — Recommendation Trust Report

**Status:** DONE  
**Execution Status:** COMPLETED  
**Approved By:** User  
**Priority:** P1

## Objective

Expose the historical truth of recommendation performance so trust is based on evidence rather than claims.

## Scope

1. Report overall success rate with sample count.
2. Report success by 1/3/5/7-day horizon with sample counts.
3. Report predicted versus actual returns.
4. Report average winning and losing returns.
5. Report performance by probability/confidence bucket.
6. Report failures and unevaluable recommendations separately.
7. Identify weak horizons and misleading confidence ranges when sample size supports the comparison.
8. Ensure every statistic is reproducible from persisted recommendation/outcome data.

## Non-goals

- Changing recommendation generation.
- Model retraining.
- Hiding or filtering failures to improve presentation.
- UI/dashboard work beyond the minimum output contract needed for the report.

## Acceptance Criteria

- [ ] Every success percentage includes its sample count.
- [ ] Failures remain visible.
- [ ] Unevaluable recommendations are reported separately.
- [ ] Horizon performance is available for supported horizons.
- [ ] Predicted vs actual return statistics are available.
- [ ] Confidence/probability bucket statistics include sample counts.
- [ ] Insufficient samples are explicitly identified.
- [ ] Tests verify report calculations against known fixtures.

## Dependency Chain

### Previous / Required
- **EPIC-006 — Positive Recommendation Performance Report** — provides the historical performance calculations.
- **EPIC-018 — Recommendation Lifecycle & Outcome Scheduler** — provides completed lifecycle/outcome data.

### Next / Unlocks
- **Future self-learning/calibration EPICs** — may use the trust report as evidence, but must be separately defined and approved.

### Chain Position

`EPIC-008 + EPIC-009 + EPIC-010 + EPIC-015 → EPIC-016 → EPIC-017 → EPIC-018 → EPIC-019`

EPIC-011 (Calibration Feedback Loop) may consume the same outcome/performance evidence and should be coordinated with EPIC-019 rather than treated as an implicit dependency.

### Execution Rule

Do not treat a recommendation as trustworthy merely because the report exists. Every statistic must expose sample size and preserve failures/unevaluable cases. Do not proceed to future self-learning work based on insufficient evidence.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-019

### Branch

autonomous/epic-m1-16, branched cleanly from `main` (both declared dependencies, EPIC-006 and EPIC-018, are already merged).

### Objective

Expose the historical truth of recommendation performance -- reusing EPIC-006's deterministic performance aggregates in full -- and additionally flag which 1/3/5/7-day horizons and predicted-probability buckets are performing weakly relative to the overall success rate, but only when each has enough evaluated samples to support that comparison.

### Design Decisions

- **No new table or migration.** EPIC-019 adds no new persisted state; it is a pure, deterministic read-side aggregation over EPIC-006's `compute_performance_report`, which itself reads only `Prediction`/`PredictionOutcome` rows (the same rows EPIC-018's scheduler populates over time). Reuses `app/performance.py` entirely rather than duplicating any of its logic (scope items 1-6 are already satisfied unchanged by EPIC-006's existing report).
- **New module `app/trust_report.py`, `compute_trust_report(session) -> TrustReport`:** wraps `PerformanceReport` with a `verdict` per horizon (`HorizonTrust`) and per probability bucket (`ProbabilityBucketTrust`) — this is the only new behavior (scope item 7).
- **Three verdicts, fixed product/policy constants (`TRUST_REPORT_VERSION = "TRUST-001"`):**
  - `INSUFFICIENT_SAMPLE` — evaluated_count for that horizon/bucket is below `MIN_SAMPLE_SIZE_FOR_COMPARISON = 20`, or the overall success rate itself has no data. Explicit, never silently omitted (satisfies the EPIC's "insufficient samples are explicitly identified" AC) and never mistaken for `OK`.
  - `WEAK` — sample size is sufficient AND `overall_success_rate - this_success_rate >= WEAKNESS_MARGIN (0.10)`, i.e. performing at least 10 percentage points below the platform-wide rate.
  - `OK` — sufficient sample, not weak.
  - Both constants are fixed, documented policy values (mirroring the pattern of `MIN_SCORE_FOR_SELECTION` in EPIC-017); either would be bumped via `TRUST_REPORT_VERSION` if changed, never silently.
- **Failures/unevaluable stay visible** exactly as EPIC-006 already reports them (`performance.failure_count`, `performance.unevaluable_count`) — EPIC-019 adds no filtering or hiding logic on top (non-goal: "hiding or filtering failures to improve presentation").
- **Reproducibility (scope item 8):** every verdict is computed from `PerformanceReport`'s already-deterministic aggregate fields with plain arithmetic (no LLM reasoning, no additional query, no randomness) — running the same persisted `Prediction`/`PredictionOutcome` rows through `compute_trust_report` twice always yields the identical report.

### Files Changed

- `app/trust_report.py` — new: `compute_trust_report`, `TrustReport`, `HorizonTrust`, `ProbabilityBucketTrust`, verdict constants.
- `tests/test_trust_report.py` — new: 7 tests.
- `docs/epics/EPIC-019-recommendation-trust-report.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_trust_report.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head is unchanged from EPIC-018's `0015_recommendation_lifecycles`)

### Test Results

- `pytest -q`: **167 passed, 0 failed** (160 pre-existing from `main` + 7 new).
- `pytest -v tests/test_trust_report.py`: **7 passed** — empty history reports `INSUFFICIENT_SAMPLE` everywhere rather than a fabricated verdict; the underlying `PerformanceReport` fields pass through `TrustReport.performance` unchanged; a horizon with real signal (5 samples, all failing) below the 20-sample floor is `INSUFFICIENT_SAMPLE`, not `WEAK`; a horizon with 20 samples at 0% success against an overall rate of 50% is correctly flagged `WEAK` while a same-size 100%-success horizon is `OK`; a horizon matching the overall rate exactly with enough samples is `OK`; a probability bucket follows the identical weak/ok logic as horizons, with every unpopulated bucket explicitly `INSUFFICIENT_SAMPLE`; and failures/unevaluable recommendations remain visible in the wrapped `performance` field.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0015_recommendation_lifecycles` (no migration in this EPIC).

### Acceptance Criteria

- [x] Every success percentage includes its sample count (inherited unchanged from EPIC-006's `PerformanceReport`/`HorizonPerformance`/`ProbabilityBucketPerformance`).
- [x] Failures remain visible (`performance.failure_count`, never filtered).
- [x] Unevaluable recommendations are reported separately (`performance.unevaluable_count`).
- [x] Horizon performance is available for supported horizons (all four `VALID_HORIZON_DAYS`, always present, via `horizon_trust`).
- [x] Predicted vs actual return statistics are available (`performance.returns`).
- [x] Confidence/probability bucket statistics include sample counts (`probability_bucket_trust`, all ten buckets always present).
- [x] Insufficient samples are explicitly identified (`VERDICT_INSUFFICIENT_SAMPLE`, distinct from both `OK` and `WEAK`).
- [x] Tests verify report calculations against known fixtures.

### Claude Assessment

I believe this implementation satisfies all eight acceptance criteria with real, verified evidence. EPIC-019 deliberately reuses EPIC-006's report wholesale rather than reimplementing any of its statistics, since the EPIC's own dependency chain lists EPIC-006 as providing "the historical performance calculations" — EPIC-019's only genuinely new contribution is the weak-horizon/weak-bucket verdict layer (scope item 7) and the explicit insufficient-sample distinction it requires. `MIN_SAMPLE_SIZE_FOR_COMPARISON` and `WEAKNESS_MARGIN` are documented design choices open to reviewer adjustment. Per the user's 2026-08-20 standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

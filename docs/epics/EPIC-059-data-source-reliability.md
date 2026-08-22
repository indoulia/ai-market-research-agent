# EPIC-059 — Data Source Reliability

Status: DONE
Execution Status: COMPLETED

## Objective
Measure the freshness, completeness, availability, and historical reliability of every external information source used by recommendations.

## Scope
- Track source freshness and latency.
- Track completeness and failures.
- Track source coverage.
- Record source reliability metrics.
- Expose evidence-quality status to downstream confidence calculations.

## Acceptance Criteria
- Every external evidence item has source and timestamp metadata.
- Stale or unavailable sources are explicitly identified.
- Reliability metrics are reproducible.
- Low-quality evidence cannot silently receive full trust.

## Dependencies
Previous: EPIC-058.
Next: EPIC-060.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-059

### Branch

autonomous/epic-m1-64, branched cleanly from `main` (the declared dependency -- EPIC-058 -- is already merged).

### Objective

Measure the freshness, completeness, availability, and historical reliability of every external information source used by recommendations, and expose an explicit evidence-quality status downstream confidence calculations can consult.

### Design

`compute_data_source_reliability_report` composes EPIC-030's `DataFetchAttempt` log (freshness/latency/completeness per data type -- scope: "track source freshness and latency"; "track completeness and failures") with EPIC-043's `RecommendationEvidenceItem` snapshots (coverage per evidence category -- scope: "track source coverage"), reusing EPIC-023's `VERDICT_OK`/`VERDICT_WEAK`/`VERDICT_INSUFFICIENT_SAMPLE` vocabulary and EPIC-019's `MIN_SAMPLE_SIZE_FOR_COMPARISON` rather than redefining either.

### Reliability & Coverage Metrics

Per data type: `success_rate` (successful vs. total fetch attempts), `average_latency_seconds` (requested-at minus source-timestamp, among successful attempts with a real timestamp), and a verdict requiring both sufficient sample and a success rate at or above `RELIABILITY_SUCCESS_THRESHOLD` (0.90) to be called `OK`. Per evidence category: `coverage_rate` (available vs. total snapshotted items), reused from EPIC-043's own `AVAILABLE`/`STALE`/`UNAVAILABLE` status vocabulary.

### Evidence-Quality Status Never Defaults to Trusted

`_quality_statuses` produces one `EvidenceQualityStatus` per data type and per evidence category, and the default for anything short of a clean `OK` verdict or sufficient coverage is always `trusted=False` with an explicit reason -- there is no code path where insufficient or weak evidence silently receives `trusted=True` (AC: "low-quality evidence cannot silently receive full trust"), proven directly by test for both an unreliable data source and a low-coverage evidence category (`FUNDAMENTAL`, always `UNAVAILABLE` per EPIC-043's own honest gap).

### Source and Timestamp Metadata

"Every external evidence item has source and timestamp metadata" (AC) is inherited from EPIC-043's own construction -- this module reads, but does not need to re-verify, that guarantee.

### Reproducibility

Purely a deterministic aggregation over EPIC-030/EPIC-043's own already-recorded data, with no randomness anywhere -- `test_report_is_reproducible` proves two calls on identical data produce an identical report (AC: "reliability metrics are reproducible"). This module writes nothing anywhere, proven directly by `test_report_never_writes_anything`.

### Files Changed

- `app/data_source_reliability.py` — new: `compute_data_source_reliability_report`, `SourceReliabilityMetric`/`EvidenceCoverageMetric`/`EvidenceQualityStatus`/`DataSourceReliabilityReport` dataclasses.
- `tests/test_data_source_reliability.py` — new: 7 tests.
- `docs/epics/EPIC-059-data-source-reliability.md` — this completion report.

No migration: pure read-side aggregation over EPIC-030/EPIC-043's existing tables.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_data_source_reliability.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0045_recommendation_alerts`, unchanged -- confirms no migration drift)

### Test Results

- `pytest -q`: **565 passed, 0 failed** (558 pre-existing from `main` + 7 new).
- `pytest -q tests/test_data_source_reliability.py -v`: **7 passed** — an empty platform reports `INSUFFICIENT_SAMPLE` everywhere and no evidence categories; a reliable source (100% success, real latency) is `OK` and `trusted`; an unreliable source (25% success) is `WEAK` and untrusted with the correct reason; evidence coverage is measured per category (fundamental always unavailable, technical/volume available); a low-coverage category is marked untrusted; the report never writes anything; the report is reproducible across two identical calls.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: passed, single head unchanged (no migration in this EPIC).

### Acceptance Criteria

- [x] Every external evidence item has source and timestamp metadata (inherited from EPIC-043's own construction).
- [x] Stale or unavailable sources are explicitly identified (`STATUS_STALE`/`STATUS_UNAVAILABLE` counts per category; `INSUFFICIENT_SAMPLE`/`WEAK` verdicts per data type).
- [x] Reliability metrics are reproducible (deterministic aggregation; proven by test).
- [x] Low-quality evidence cannot silently receive full trust (`trusted=False` is the default for anything short of a clean `OK` verdict or sufficient coverage; proven by test).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including direct proof that an unreliable source and a low-coverage evidence category are both explicitly marked untrusted rather than defaulting to trusted. This EPIC composes EPIC-030's fetch-attempt log and EPIC-043's evidence snapshots into one reliability report, reusing EPIC-019/EPIC-023's existing evidence-gating vocabulary, without duplicating or modifying either source module. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

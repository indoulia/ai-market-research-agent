# EPIC-M1.12 — Market Universe & Daily Candidate Scan

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
**Priority:** P1

## Objective

Automatically scan the supported NSE universe each trading day and produce a deterministic candidate set for downstream evaluation.

## Scope

1. Define the eligible NSE universe using available persisted/security data.
2. Identify the trading date and prevent duplicate daily scans.
3. Run the existing feature/prediction pipeline across eligible securities.
4. Exclude missing, stale, or invalid market data explicitly.
5. Persist or expose the candidate set with scan timestamp/date and data/model versions.
6. Make the scan idempotent for the same trading date and universe version.
7. Add deterministic tests for eligibility, stale data, duplicates, and empty candidate sets.

## Non-goals

- Final positive recommendation generation.
- New ML model training.
- Portfolio/trading automation.
- UI/dashboard work.
- ChatGPT-assisted discovery.

## Acceptance Criteria

- [ ] A versioned/traceable NSE universe can be scanned.
- [ ] Each eligible security is evaluated at most once per scan.
- [ ] Stale/invalid data is explicitly excluded and observable.
- [ ] Re-running the same scan does not create duplicate scan results.
- [ ] Candidate results retain scan date and relevant data/model versions.
- [ ] Empty/partial scans are handled without fabricating candidates.
- [ ] Tests cover normal, duplicate, stale-data, and empty-universe cases.

## Dependency Chain

### Previous / Required
- **M1.3 — Yahoo NSE Historical Data Provider** — supplies the market data required by the scan.
- **M1.8 — Positive Consensus Engine** — provides the qualifying criteria used downstream.

### Next / Unlocks
- **M1.13 — Positive Recommendation Generator** — consumes the candidate set produced by this EPIC.

### Chain Position

`M1.3 + M1.8 → M1.12 → M1.13 → M1.14 → M1.15 → M1.16`

M1.17 (ChatGPT Candidate Discovery) branches later from the same quantitative path and depends on M1.8 and M1.13.

### Execution Rule

Do not execute M1.13 until M1.12 is implemented, reviewed, and merged. If implementation exposes a dependency defect, report it; do not silently bypass the dependency.

## Completion Report

<!-- Claude: populate only after implementation. Preserve review history. -->

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

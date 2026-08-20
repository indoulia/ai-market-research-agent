# EPIC-M1.18 — Watchlist Intake

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
**Priority:** P1

## Objective
Establish a deterministic, persistent intake boundary for stocks that users or other discovery sources want the recommendation system to monitor.

## Scope
1. Define a watchlist entry contract for symbol, source, timestamp, and active state.
2. Validate symbols against the supported NSE/security universe.
3. Make repeated intake idempotent.
4. Preserve watchlist history rather than silently overwriting prior intake events.
5. Expose enough persisted context for downstream watchlist analysis.
6. Add deterministic tests for valid, invalid, duplicate, inactive, and unknown-symbol cases.

## Non-goals
- Generating recommendations.
- Changing positive-consensus rules.
- Automatic trading.
- Learning from outcomes.
- UI/dashboard implementation.

## Acceptance Criteria
- [ ] Valid watchlist entries are persisted with provenance and timestamps.
- [ ] Unsupported symbols are rejected explicitly.
- [ ] Duplicate intake is idempotent.
- [ ] Historical intake information is auditable.
- [ ] Active/inactive state is deterministic.
- [ ] Tests cover normal and boundary cases.

## Dependency Chain
### Previous / Required
- **M1.12 — Market Universe & Daily Candidate Scan** — establishes the supported market/security universe.
- **M1.17 — ChatGPT Candidate Discovery** — establishes the external discovery/provenance pattern where applicable.

### Next / Unlocks
- **M1.19 — Watchlist Positive Analysis**

### Chain Position
`M1.12 + M1.17 → M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Do not execute until dependencies are implemented, reviewed, and merged. Watchlist intake must remain an input/provenance boundary and must not bypass quantitative qualification.

## Completion Report
Update this section with implementation evidence, tests, merge/PR information, and final status before marking the EPIC implemented.

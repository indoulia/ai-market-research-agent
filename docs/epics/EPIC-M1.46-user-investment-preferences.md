# EPIC-M1.46 — User Investment Preferences

**Status:** READY_FOR_APPROVAL  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.14

## Objective
Allow each user to define investment preferences that control recommendation discovery, scoring, ranking, and default horizon without changing the underlying historical truth or recommendation contract.

## Scope
- Default horizon: short term (1–7 days).
- Support short, medium, long, and custom horizons.
- Store risk preference and minimum confidence threshold.
- Support market-cap/sector preferences without forcing them.
- Apply preferences consistently to discovery and recommendation selection.
- Preserve the preference snapshot used when a recommendation is generated.

## Acceptance Criteria
- New users default to short-term 1–7 day recommendations.
- A user can change horizon and supported preferences.
- Recommendation generation records the effective preference snapshot.
- Preference changes do not mutate historical recommendations.
- Invalid preference combinations are rejected clearly.
- Tests cover defaults, persistence, overrides, and historical immutability.

## Dependency Chain
M1.14 → M1.46 → M1.47+

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->

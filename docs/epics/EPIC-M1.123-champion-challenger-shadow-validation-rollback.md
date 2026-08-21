# EPIC-M1.123 — Champion/Challenger Shadow Validation & Rollback

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Allow new models, calibrators, ranking policies and provider strategies to prove themselves in shadow mode against the production champion before they can affect user-facing recommendations, with deterministic promotion and rollback.

## Scope
- Define Champion and Challenger model identities and lifecycle states.
- Run challengers in shadow mode using the same point-in-time inputs as the champion.
- Record both outputs without allowing challenger output to alter production recommendations.
- Compare calibration, accuracy, usefulness, stability, latency, cost and regime/horizon performance.
- Require minimum sample sizes and predefined promotion gates.
- Protect untouched holdout and future/live validation periods.
- Support staged promotion and observation windows.
- Detect production regression after promotion.
- Support immediate rollback to the last known-good champion.
- Version and preserve all promotion/rollback decisions.
- Extend the same mechanism to provider-routing and ranking-policy candidates where appropriate.

## Acceptance Criteria
- A challenger cannot affect production recommendations while in shadow mode.
- Champion and challenger consume equivalent eligible evidence.
- Promotion requires predefined statistical and business-quality gates.
- Regression automatically triggers rollback or recommendation suppression according to policy.
- Every promotion/rollback is reproducible and auditable.
- Historical predictions remain tied to the exact champion/provider/configuration used at decision time.

## Dependencies
M1.83, M1.88, M1.100, M1.115.

## Non-Goal
No automatic promotion based solely on a single metric or short recent streak.

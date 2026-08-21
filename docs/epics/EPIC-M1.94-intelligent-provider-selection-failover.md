# EPIC-M1.94 — Intelligent Provider Selection & Failover

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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

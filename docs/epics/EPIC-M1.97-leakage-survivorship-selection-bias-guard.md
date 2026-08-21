# EPIC-M1.97 — Leakage, Survivorship & Selection-Bias Guard

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Make look-ahead, survivorship and selection bias detectable and blocking for training, replay and evaluation workflows.

## Scope
- Detect future-dated inputs relative to prediction timestamps.
- Validate point-in-time dataset membership.
- Include historically eligible securities rather than only today's survivors.
- Detect post-decision data revisions and leakage paths.
- Validate discovery/selection stages independently from published recommendations.
- Produce blocking violations with evidence and reason codes.
- Add adversarial leakage fixtures and regression tests.

## Acceptance Criteria
- Known leakage scenarios fail deterministically.
- Historical evaluation uses the correct point-in-time universe.
- Published-only evaluation cannot masquerade as universe-level performance.
- Leakage checks run automatically before validation/training.
- Overrides require explicit, auditable justification and cannot silently bypass production gates.

## Dependencies
Previous: M1.24, M1.25, M1.95, M1.96.
Next: M1.98.

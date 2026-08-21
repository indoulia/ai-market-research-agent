# EPIC-M1.92 — Provider Registry & Configuration

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P0

## Objective
Provide centralized, capability-aware provider registration and configuration so provider choice can change without modifying MRA business logic.

## Scope
- Create provider registry keyed by capability.
- Configure primary, secondary and optional providers per capability.
- Support enable/disable, credentials, endpoints, quotas and timeouts.
- Support capability-level routing rather than one global provider.
- Preserve provider version/configuration identity in evidence and prediction history.
- Validate configuration before runtime use.
- Support safe configuration changes without rewriting historical records.

## Acceptance Criteria
- Provider selection is configuration-driven.
- Different MRA capabilities can use different providers.
- Invalid provider configurations fail clearly before use.
- Historical records preserve the provider actually used.
- No business logic contains provider-selection branches.

## Dependencies
Previous: M1.91.
Next: M1.93.

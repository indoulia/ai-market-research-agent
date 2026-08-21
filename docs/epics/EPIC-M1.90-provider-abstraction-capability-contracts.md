# EPIC-M1.90 — Provider Abstraction & Capability Contracts

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_READY
**Priority:** P0

## Objective
Make every external-world capability in MRA provider-based so domain and recommendation logic never depends directly on a specific vendor.

## Scope
- Define provider contracts for AI/discovery, market data, fundamentals, news, events and other external information sources.
- Separate provider adapters from domain/business logic.
- Define normalized capability-level request/response contracts.
- Preserve provenance, timestamps, provider identity and version metadata.
- Support provider-specific failures without leaking vendor types into domain code.
- Define capability availability and health contracts.
- Require at least three interchangeable implementation slots per provider capability at architecture/test level.
- Add contract and substitution tests.

## Acceptance Criteria
- No domain service directly calls a named external provider SDK/API.
- Provider implementations are replaceable behind stable contracts.
- Provider metadata and provenance are preserved.
- A provider can be disabled without changing recommendation/business logic.
- Contract tests prove interchangeable implementations.

## Dependencies
Previous: M1.72, M1.73, M1.35.
Next: M1.91.

## Architectural Invariant
**All external-world access MUST go through provider contracts.** Direct vendor coupling in domain/business logic is prohibited.

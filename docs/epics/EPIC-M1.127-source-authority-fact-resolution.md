# EPIC-M1.127 — Source Authority & Fact Conflict Resolution

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Resolve conflicting external facts using explicit source authority, freshness, provenance and fact-type policies rather than simple provider majority voting.

## Scope
- Define authority policies by fact type: price, corporate action, filing, financial result, event, news and other evidence.
- Distinguish authoritative primary sources from secondary aggregators and syndicated copies.
- Detect conflicting values across providers.
- Detect duplicated/syndicated evidence so it does not falsely increase consensus.
- Apply timestamp and effective-date precedence rules.
- Preserve all conflicting observations rather than deleting them.
- Produce a resolved fact with reason, source authority and confidence.
- Allow manual governance of authority rules without rewriting historical facts.

## Acceptance Criteria
- A provider majority cannot automatically override a configured authoritative source.
- Conflicting facts remain auditable.
- Resolved facts include provenance and resolution reason.
- Historical resolutions are immutable and versioned.
- Fact-resolution output can be consumed by prediction and learning systems.

## Dependencies
M1.90, M1.94, M1.103, M1.120.

## Architectural Rule
**Consensus is evidence; authority is policy. They must never be conflated.**

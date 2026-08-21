# EPIC-M1.120 — Event-Driven Market Intelligence Refresh

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Ensure MRA reacts to material external-world changes instead of waiting for the next scheduled refresh.

## Scope
- Detect new material news through provider contracts.
- Detect corporate actions and earnings/events through provider contracts.
- Detect material market/sector movements.
- Map events to affected securities and active predictions.
- Classify materiality, freshness and affected horizon.
- Trigger targeted re-fetch and re-analysis through M1.118.
- Deduplicate repeated/syndicated events.
- Preserve event provenance and detection timestamps.
- Avoid unnecessary re-analysis for immaterial events.
- Handle provider disagreement and fallback.

## Event Classes
- News
- Corporate action
- Earnings/results
- Material company event
- Material market movement
- Material sector/industry movement
- Provider/data correction

## Acceptance Criteria
- Material events can trigger analysis without waiting for the next scheduled cycle.
- Event-to-security mapping is deterministic and auditable.
- Duplicate events do not create duplicate revisions.
- Event-triggered predictions preserve prior versions.
- Event freshness and provider provenance are recorded.
- Event-driven execution respects configured rate/cost controls.

## Dependencies
M1.73, M1.90, M1.94, M1.106, M1.118.

## Architectural Rule
**Events trigger capabilities through orchestration; event providers never call recommendation/domain services directly.**

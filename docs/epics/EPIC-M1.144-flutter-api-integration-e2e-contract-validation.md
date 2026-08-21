# EPIC-M1.144 — Flutter/API Integration & End-to-End Contract Validation

**Track:** CROSS-TRACK
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Prove that the Flutter application and MRA APIs operate as one coherent product with no contract drift, inconsistent state handling or platform-specific behavior.

## Scope
- Generate/use typed Flutter API client from M1.132 OpenAPI contract.
- Replace fixtures with live API responses behind environment configuration.
- Contract compatibility tests in CI.
- API mock server/fixtures for UI development.
- End-to-end flows: launch → recommendations → detail → history → event → feedback → preferences.
- Error states: unauthorized, rate limited, timeout, stale data, provider unavailable, server error, empty result.
- Offline/reconnect behavior where supported.
- Deep-link tests on web.
- Responsive tests at representative widths rather than device-specific assumptions.
- Verify exact target/SL/trust/confidence values shown in UI match API payloads.

## Acceptance Criteria
- Breaking API changes fail CI before UI merge.
- UI never silently falls back to stale fixture data in production builds.
- Every primary user journey has an automated happy-path and failure-path test.
- Web deep links work after reload.
- Mobile and web render the same domain truth with adaptive presentation.
- API/UI release compatibility is explicitly versioned.

## Parallelization
Cross-track integration. API and UI teams can work independently until contract integration begins.

## Dependencies
M1.132, M1.133, M1.134, M1.135, M1.136, M1.137, M1.138, M1.139, M1.140, M1.141, M1.142, M1.143.

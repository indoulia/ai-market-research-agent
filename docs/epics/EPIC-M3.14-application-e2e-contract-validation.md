# EPIC-M3.14 — Application E2E Contract Validation

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Prove that Flutter screens and MRA APIs implement the same contracts and that critical user journeys work end-to-end on web and mobile.

## Scope
- Contract compatibility tests between API schemas and Flutter models.
- API integration tests.
- Flutter widget/golden tests for critical layouts.
- End-to-end tests for dashboard, explorer, detail, tracking, feedback and authentication.
- Loading/empty/error/stale-data scenarios.
- Prediction revision and target/SL state transitions.
- Responsive viewport coverage.
- Accessibility smoke tests.
- Performance smoke tests.

## Required Journeys
1. Login → Home.
2. Home → Opportunity Explorer → Detail.
3. Detail → Prediction Timeline.
4. Detail → Feedback.
5. Home → News/Event → affected prediction.
6. Active prediction → target/SL update.
7. Trust dashboard → historical breakdown.
8. Discovery → candidate → recommendation.

## Acceptance Criteria
- No critical contract mismatch remains.
- Critical journeys pass on representative web and mobile viewports.
- API errors render consistently.
- Historical/revision data is displayed without mutation.
- E2E tests are repeatable in CI.

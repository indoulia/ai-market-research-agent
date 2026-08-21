# EPIC-M1.132 — MRA Application Platform Foundation

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Establish the production-quality Flutter application foundation and API/BFF boundary for a responsive MRA client running on mobile and web.

## UI Scope
- Flutter application structure with feature-based modules.
- Material 3 foundation with a restrained professional visual language.
- Typography, spacing, elevation, iconography, semantic states and sizing tokens.
- Responsive breakpoints based on available window size, not device labels.
- Light/dark theme architecture if supported by existing product requirements.
- Desktop/web, tablet and mobile layouts.
- Central navigation, routing, error boundary and loading-state conventions.
- Typed API client generation/adapter boundary.
- Avoid business logic and provider logic inside widgets.

## API Contract
Base: `/api/v1`

Required foundation behavior:
- Versioned API envelope/error contract.
- Correlation/request ID.
- Authentication/session context.
- Consistent pagination/filter/sort conventions.
- RFC-style validation/error representation.
- Health/readiness endpoint.
- API capability/version discovery.

Representative endpoints:
- `GET /api/v1/health`
- `GET /api/v1/version`
- `GET /api/v1/capabilities`

## Acceptance Criteria
- Flutter app starts cleanly on supported mobile and web targets.
- Responsive layout adapts without device-specific branching.
- API contracts are versioned and machine-readable.
- UI and API use typed DTOs/contracts rather than ad-hoc JSON assumptions.
- Global loading, error, empty and retry states are standardized.
- No screen embeds backend/provider implementation details.

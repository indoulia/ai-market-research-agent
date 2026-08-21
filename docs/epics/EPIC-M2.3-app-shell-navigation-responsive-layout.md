# EPIC-M2.3 — Flutter App Shell, Navigation & Responsive Layout [UI]

**Status:** SUPERSEDED BY M3.1
**Execution Status:** NOT_EXECUTED
**Priority:** P0
**Parallel Track:** UI

> **2026-08-22 — superseded, not implemented (explicit user decision).** `EPIC-M3.1-mra-application-platform-foundation.md`
> recreates this same API contract + Flutter design system + app shell foundation as part of the combined M3.1-M3.15
> vertical-slice roadmap (see `EPIC-M3-ROADMAP-NOTE.md`). Implementing this EPIC would duplicate that foundation work.
> M3 is the authoritative application/UI roadmap going forward. This file is preserved for history, not deleted.

## Objective
Build the application shell that feels natural on phone, tablet and web while keeping navigation simple and avoiding dashboard clutter.

## Scope
- Responsive shell using available window width.
- Small screens: bottom navigation / compact navigation.
- Medium/large screens: NavigationRail or side navigation.
- Wide web: constrained content width with intentional columns, not full-width stretching.
- Route/deep-link architecture.
- Persistent selected state and scroll restoration.
- Global app bar/search/context actions.
- Desktop mouse, keyboard and touch behavior.
- Loading/error/offline shell states.
- Authentication/session boundary.

## Primary Destinations
1. Home / Recommendations
2. Discover
3. Watchlist / Tracking
4. History / Performance
5. Settings

Avoid adding top-level destinations for every minor capability.

## Acceptance Criteria
- Same route model works on mobile and web.
- Navigation changes by available window width rather than device detection.
- Deep links open the correct stock/prediction detail.
- Browser back/forward works correctly.
- UI state survives resize/orientation changes.
- No horizontal overflow at supported widths.

## API Contract Dependency
Consumes M2.1 session/profile and route-resource APIs; no UI-specific API endpoints may be invented outside the API contract.

## Dependencies
M2.1, M2.2.

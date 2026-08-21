# EPIC-M1.143 — Responsive, Accessibility & Performance Quality

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Ensure the Flutter app is genuinely production-quality across mobile and web: responsive, accessible, smooth, fast and visually dense without becoming cluttered.

## Scope
- Responsive breakpoints based on available window constraints.
- Mobile portrait/landscape and resizable-window support.
- Web desktop and narrow-window support.
- Keyboard navigation, tab order, hover/tooltips, context behavior and mouse wheel support.
- Touch targets and gesture behavior.
- Safe areas and text scaling.
- Screen-reader semantics for key controls and values.
- Lazy loading/pagination for large datasets.
- Avoid unnecessary rebuilds and expensive chart rendering.
- Preserve scroll/list state during navigation and refresh.
- Loading skeletons and optimistic/instant UI transitions where safe.
- Performance budgets for startup, screen transition, API rendering and scrolling.

## Acceptance Criteria
- No critical screen requires horizontal page scrolling.
- No layout is selected from hard-coded device type.
- Main dashboard remains smooth with realistic recommendation/news datasets.
- Keyboard-only web navigation works.
- Text scaling does not destroy critical information hierarchy.
- Accessibility semantics exist for score, Trust, confidence, target and SL.
- Performance regression tests are documented.

## Parallelization
UI quality team; may run after the first screen implementations and in parallel with API hardening.

## Dependencies
M1.133, M1.134, M1.136, M1.138, M1.140, M1.142.

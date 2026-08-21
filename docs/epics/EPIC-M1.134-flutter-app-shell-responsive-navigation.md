# EPIC-M1.134 — Flutter App Shell & Responsive Navigation

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Build the application shell that feels native on mobile and professional on web without duplicating the application. Layout must adapt to available window size rather than hard-coded phone/tablet/desktop assumptions.

## Navigation
Primary destinations:
1. Home / Opportunities
2. Discover
3. Tracking
4. Market / News
5. History
6. Settings

Mobile: compact bottom navigation with high-value destinations and secondary actions in sheets/menus.
Web/large screens: navigation rail/sidebar with persistent context.

## Shell Requirements
- Global top bar with title/context and minimal actions.
- Global search entry where appropriate.
- Refresh state and last-updated indicator.
- User/profile/preferences entry.
- Global error/offline state.
- Deep-linkable routes for recommendation and history views.
- State restoration when navigating back/forward.
- Keyboard shortcuts and mouse hover/tooltips on web.
- Safe areas and accessibility support.

## Layout Rules
- Never fill wide screens with stretched cards/text; use constrained grids and max-width containers.
- Prefer grid/two-column detail layouts on wide screens.
- Collapse progressively on narrow windows.
- Preserve information priority when reducing columns.
- Avoid orientation-specific logic; branch on available constraints.

## Acceptance Criteria
- One Flutter codebase runs mobile and web.
- Navigation changes appropriately at responsive breakpoints.
- Routes are deep-linkable on web.
- Back/forward/navigation state is preserved.
- Shell passes keyboard, touch and screen-size tests.
- No screen introduces its own navigation system.

## Parallelization
UI shell team. Can proceed with API team after M1.132 contract is established.

## Dependencies
M1.132, M1.133.

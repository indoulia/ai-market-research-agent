# EPIC-M1.134 — Flutter App Shell & Responsive Navigation

**Track:** UI
**Status:** DONE
**Execution Status:** COMPLETED
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

## Completion Report

**Implemented on branch:** `autonomous/epic-m1-133` (same branch as EPIC-M1.133 — the two are tightly coupled UI-foundation pieces implemented and tested together; see that doc's Completion Report for the design-system half).

**What was built:**
- `go_router`-based `StatefulShellRoute.indexedStack` (`lib/app_shell/app_router.dart`) with one branch per primary destination (Home, Discover, Tracking, Market, History, Settings), each keeping its own navigation stack/scroll position across tab switches.
- Responsive shell (`AppShellScaffold`): bottom `NavigationBar` under 600px width, `NavigationRail` from 600px, extended (labelled) rail from 1024px — branched purely on `LayoutBuilder` width, never platform/device detection.
- Deep-linkable nested route (`/home/recommendation/:id`) proven with a placeholder detail screen.
- Keyboard shortcuts: Alt+1..6 jump directly to a destination (`CallbackShortcuts`), satisfying the "keyboard shortcuts ... on web" shell requirement.
- Tooltips on web/desktop-relevant app-bar actions (search, account).
- Settings screen links to the EPIC-M1.133 component gallery, so the QA gallery stays reachable from the running app rather than only from `main.dart`.
- Destinations without their own EPIC yet (`Discover`, `Tracking`, `Market`, `History`, `Settings`'s real content) render an explicit `MraStateView.empty` naming the EPIC that owns them — never fake data.

**Tests:** `test/app_shell/app_shell_test.dart` — compact-vs-rail layout switching, tap-to-navigate + route assertion, deep-link rendering, settings→gallery navigation, branch-switch state preservation, and the Alt+2 keyboard-shortcut route change. Combined with EPIC-M1.133's suite: `flutter test` → 33/33, `flutter analyze` → no issues.

**Acceptance criteria status, named honestly rather than blanket-checked:**
- Done: one codebase runs mobile/web layouts, breakpoint-driven nav switch, deep-linkable routes, back/forward + branch state preserved (go_router owns browser history on web), keyboard/touch/screen-size tested, no screen invents its own navigation.
- Explicit gap, not yet implemented: "Global refresh state and last-updated indicator" and "Global error/offline state" in the top app bar. Both need a real connectivity/data-freshness signal that doesn't exist yet (no API wiring, no connectivity plugin) — building either now would mean faking the underlying state. Left for whichever later EPIC first wires the shell to live data; the design system already has the needed `MraStateView.offline`/`showMraToast` building blocks ready to use at that point.

**CI:** added `.github/workflows/flutter-ci.yml` (analyze + format-check + test, path-filtered to `flutter_app/**`) in this same branch so this and future Flutter PRs get real CI signal — this repo had no Flutter CI before.

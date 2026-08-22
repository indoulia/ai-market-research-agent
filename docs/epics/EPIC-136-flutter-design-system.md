# EPIC-136 — Flutter MRA Design System & Component Library

**Track:** UI
**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Create a clean, dense, professional Flutter design system shared by every MRA screen across mobile and web. Avoid one-off styling and visual inconsistency.

## Design Direction
- Material 3 foundation with a deliberately restrained professional financial-product visual language. Flutter Material 3 is the current default and supports adaptive components and large-screen layouts. citeturn0search1turn0search2
- Professional readable typography with clear numeric hierarchy.
- Compact information-dense cards and grids without cramped touch targets.
- Consistent iconography using one coherent icon family; icons must communicate state/action and never replace essential text.
- Limited color palette; semantic colors reserved for positive, warning, error, neutral and market-state meaning.
- Subtle elevation, borders and motion; no decorative animation that consumes attention.
- Consistent spacing, radii, density, chart styles, number formatting and empty/loading/error states.

## Components
- App shell/navigation
- KPI/stat cards
- Recommendation cards
- Dense data grids/tables
- Chips/tags
- Score/confidence/trust indicators
- Target/SL badges
- Horizon selectors
- Filter bars
- Search
- Tabs
- Bottom sheets/dialogs
- Timeline/event rows
- News cards
- Charts
- Skeleton loaders
- Empty/error/offline states
- Toast/snackbar feedback

## Responsive Rules
Use available window size, not device type, to choose layout. Use adaptive navigation and grid column behavior; mobile can use bottom navigation while larger windows can use navigation rail/sidebar. Flutter explicitly recommends measuring available window space and adapting layout accordingly. citeturn0search0turn0search3

## Acceptance Criteria
- All screens consume shared tokens/components.
- No arbitrary per-screen colors, font sizes or spacing values without documented exception.
- Components work with mouse, keyboard and touch.
- Text scaling/accessibility does not break layout.
- Light/dark themes are supported by tokens.
- Component gallery demonstrates every shared component.

## Parallelization
UI-only EPIC. It may proceed in parallel with API work using fixture data from EPIC-135.

## Dependencies
EPIC-135.

## Completion Report

**Implemented on branch:** `autonomous/epic-m1-133` (isolated worktree, parallel to the API-track session's own EPIC-135 branch).

**What was built:**
- Design tokens: `lib/design_system/tokens/` — colors (semantic roles resolved per-brightness via `MraColorScheme`, plus distinct market-up/down/flat colors), spacing/radii/elevation/motion, responsive breakpoints (`MraBreakpoints`/`MraWindowClass`), typography scale with tabular-figure numeric styling for price/percentage alignment in dense grids.
- Theme: `lib/design_system/theme/mra_theme.dart` builds light/dark `ThemeData` from those tokens (Material 3, `ColorScheme.fromSeed`) — no screen constructs its own `ThemeData`.
- Component library (`lib/design_system/components/`): `MraCard`, `MraChip` (5 semantic tones, each pairs an optional icon with color so meaning is never color-only), `KpiStatCard`, `RecommendationCard` (presentation-only view model — does not call any API), `MraDenseTable`, `ScoreIndicator` (score/confidence/trust), `TargetSlBadge`, `HorizonSelector`, `MraFilterBar`, `MraSearchField`, `MraTabBar`, bottom-sheet/dialog helpers, `TimelineEventRow`, `NewsCard`, a dependency-free `SparklineChart` (`CustomPainter`), `SkeletonBox`/`SkeletonCard` (shimmer skipped under `MediaQuery.disableAnimations`), `MraStateView` (empty/error/offline, internally scrollable so it never overflows in a squeezed slot), `showMraToast`.
- Component gallery (`lib/gallery/gallery_screen.dart`) demonstrating every shared component, reachable at runtime via Settings → "Design system gallery (QA)".

**Tests:** `test/design_system/` — component smoke tests (every component renders and responds to interaction), a text-scaling/overflow regression test (2x `TextScaler`), a responsive-breakpoint classification test, and a theme test (light/dark both build, tones differ per brightness, reduced-motion honored). All pass: `flutter test` → 33/33 (shared suite with EPIC-137, see that doc). `flutter analyze` → no issues. `dart format --set-exit-if-changed` → clean.

**Real bugs found and fixed during implementation** (not just cosmetic): a `RenderFlex`/unbounded-height crash in `TimelineEventRow`'s connector line when used inside a scrolling list (fixed with `IntrinsicHeight`); a text-not-wrapped-in-Expanded overflow in `RecommendationCard`'s footer row at 2x text scale; a vertical overflow in `MraStateView` when squeezed into a short box (fixed by making it internally scrollable); a missing-onAction test bug.

**Known gap, named rather than papered over:** this doc's "Design Direction"/"Responsive Rules" sections carry leftover literal citation-marker text (`citeturn0search...`) from whatever generated the original doc — cosmetic only, doesn't affect scope, left in place rather than risking a bad edit to a doc a peer session may also be reading concurrently.

**Fixture/mock-data note:** built before the real OpenAPI contract (EPIC-135) merged; `RecommendationCard` and friends take a plain Dart view-model (`RecommendationCardData`), so wiring real API responses in later UI epics is a mapping step, not a component rewrite.

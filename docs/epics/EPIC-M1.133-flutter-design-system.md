# EPIC-M1.133 — Flutter MRA Design System & Component Library

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
UI-only EPIC. It may proceed in parallel with API work using fixture data from M1.132.

## Dependencies
M1.132.

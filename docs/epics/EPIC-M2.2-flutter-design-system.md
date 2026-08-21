# EPIC-M2.2 — Flutter Cross-Platform Design System [UI]

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0
**Parallel Track:** UI

## Objective
Create a clean, crisp, professional MRA visual language shared across mobile and web, with responsive widgets, typography, spacing, motion and accessibility defined as reusable design tokens/components.

## Design Direction
- Professional financial-research product, not a trading-game aesthetic.
- High information density on desktop without clutter.
- Touch-first mobile interaction with progressive disclosure.
- Clear hierarchy: recommendation → target/SL → confidence/trust → evidence → history.
- Restrained color use; positive emphasis must remain accessible and not rely on color alone.
- Consistent typography, spacing, radius, elevation and iconography.

## Scope
- Material 3 foundation and theme customization.
- Typography scale and numeric/financial typography rules.
- Color roles for positive, neutral, warning, error, selected and market states.
- Spacing/grid tokens.
- Card, table, metric, badge, chart, chip, tab, filter and empty-state components.
- Skeleton/loading states.
- Error/retry states.
- Motion rules for navigation, updates and state changes; no distracting animation.
- Accessibility: contrast, text scaling, semantics, keyboard/focus behavior.
- Responsive breakpoints based on available window size, not device type.

## Acceptance Criteria
- Components are reusable rather than screen-specific.
- Mobile and desktop use the same design tokens.
- No arbitrary per-screen font sizes or spacing.
- UI remains usable at narrow, medium and wide window sizes.
- Motion has reduced-motion behavior.
- Design-system gallery/demo exists for QA.

## Dependencies
None; may run in parallel with M2.1.

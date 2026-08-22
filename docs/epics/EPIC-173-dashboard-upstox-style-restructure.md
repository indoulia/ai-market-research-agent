# EPIC-173 — Dashboard Restructure: Upstox-Pro Layout in Marksy Tokens

**Status:** IN_PROGRESS
**Source:** User request (no GitHub issue) — iterative design review in-session, approved design
reference below. Renumbered directly into the canonical `docs/epics/EPIC-NNN-*.md` sequence per
the user's standing 2026-08-22 instruction (see `feedback_keep_epic_numbers_in_canonical_sequence`
memory) — no ad hoc name was ever used for this one.
**Track:** Flutter UI
**Priority:** MEDIUM
**Product:** MRA / Marksy

## Design reference

**[Marksy Dashboard Redesign](https://claude.ai/code/artifact/dc85a4ea-4aa3-4520-84db-4b657c6a38bd)**
— the approved HTML mockup (desktop + mobile, light/dark) this epic implements. Built entirely from
this repo's real tokens (`MraColors`, `MraTypography`) and annotated zone-by-zone against the real
widget each zone maps to. Treat it as the source of truth for layout/spacing intent; treat this doc
as the source of truth for what's actually in scope for Phase 1 vs. deferred.

## Objective

`DashboardScreen` (`flutter_app/lib/features/dashboard/dashboard_screen.dart`) is currently one long
scrolling column: header → four stacked filter rows → a card grid. Restructure it into the three-zone
workspace pattern `pro.upstox.com/home` uses — brand chrome, a working center column, a fixed "watch"
rail — expressed entirely in Marksy's own tokens, reusing every existing widget rather than inventing
a new visual language.

## Scope

### Phase 1 (this epic — real data only, no fabricated widgets)

1. **Consolidated toolbar** — `HorizonSelector` + the two `MraFilterBar`s + `MraSearchField` move from
   four stacked full-width rows into one wrapped toolbar row. Same state (`_selectedHorizon`/`_market`/
   `_sizeBucket`/`_sector`), same widgets, layout only.
2. **"How Marksy works" strip** — new, dismissible (session-only for Phase 1; persisting the dismissal
   via a preferences flag is a fast-follow, not blocking) — score → target/stop-loss → tracked outcome,
   so the Trust framing is explained before a first-time user scans cards.
3. **Right "watch" rail**, visible at `MraWindowClass.expanded`/`large` (≥1024px, matching
   `AppShellScaffold`'s own extended-rail threshold) as a fixed-width column beside the grid; folds
   below the grid at `medium`/`compact`:
   - **Performance card** — merges the existing `DashboardTrustSummary` with `TrackingSummary`'s
     `targetHitRate`/`closedCount` (new `TrackingRepository.fetchSummary` call from this screen). If
     the tracking summary fails/is unavailable, the card still renders trust-only — never blocks on it,
     never fabricates a hit-rate.
   - **Activity card**, tabbed (`MraTabBar`): "Recently changed" (existing `snapshot.recentChanges`)
     and "Closed calls" (new — `TrackingRepository.fetchPredictions(status: 'CLOSED')`, small page).
   - **Important events** — existing `_EventsStrip` content, reflowed vertical for the rail.
   - **Coming soon card**, tabbed: IPO / NFO. Static placeholder content only — no IPO/NFO data source
     exists anywhere in this codebase. Same "honest gap" pattern `AppDestination.ownerEpic` already
     uses for unbuilt screens, just inline rather than a routed destination (adding IPO/NFO as real nav
     destinations + routes is explicitly deferred, see below).
4. **Dense mobile opportunity list** — at `MraWindowClass.compact`, replace the single-column full
   `RecommendationCard` list with a new compact row (`RecommendationListTile` or a `dense` mode on the
   existing card): shrunk score ring, no sparkline, target/SL collapsed to one line. Roughly 2× the
   opportunities visible per scroll on a phone. `medium`/`expanded`/`large` keep the existing card grid
   unchanged.
5. **Themed scrollbars** — add a `scrollbarTheme` to `MraTheme` (light + dark) so the app's own
   scrollbars (web/desktop) use a thin, translucent, surface-tinted thumb instead of the platform
   default, app-wide — not just the dashboard.

### Explicitly deferred (documented, not built — no fabricated data)

- **Index ticker** (NIFTY/SENSEX/BANK NIFTY) — `DashboardSnapshot`'s own doc comment confirms
  `indexes` is always `[]` today; no index-level price feed exists. Needs its own ingest epic.
- **Market movers / sector pulse** — no market-wide day-change or sector-aggregate source exists.
  Small new read model, but real backend work — not a layout change.
- **Global top-bar changes** (NSE open/closed pill, notifications) — `_MarketStatusRow`'s own comment
  already documents why `marketStatus` can be `"UNKNOWN"` (no market-calendar module yet); a "NSE Open"
  pill would fabricate certainty the app doesn't have. Top bar (`AppShellScaffold`/`_ShellAppBar`) is
  unchanged in this epic.
- **IPO/NFO as real nav destinations + screens** — the mockup's left-rail "IPO" item with a badge is
  not built; the coming-soon content lives inline in the dashboard rail instead (item 3 above).
- **Watchlist** — flagged during design review as the one thing Upstox's own home page is actually
  built around; Marksy has no watchlist feature or epic today. Left out rather than faked. A candidate
  for its own future epic, not silently added here.
- **Holdings / P&L** — Marksy's Upstox integration (EPIC-171) is market-data ingest only, no order
  execution. A holdings widget would claim a capability the product doesn't have; not added.

## Non-goals

No backend/API changes. No new destinations/routes. No changes to `RecommendationCard`'s existing
(non-compact) presentation or to the opportunities-grid data flow.

## Acceptance criteria

- Filter/search state and behavior are unchanged from the user's perspective; only layout moves.
- At `expanded`/`large` width, Performance/Activity/Events/Coming-soon render in a fixed-width column
  beside the opportunities grid; at `medium`/`compact` they render stacked below it.
- Activity and Coming-soon tabs switch content without a network re-fetch of already-loaded data.
- Performance card degrades gracefully (trust-only) if the tracking-summary fetch fails.
- At `compact` width, opportunities render as the new dense row, not the full card.
- `flutter analyze` and `dart format --output=none --set-exit-if-changed` are clean; existing
  `dashboard_screen_test.dart` suite still passes; new widget tests cover the tab switches, the
  dismissible strip, the Performance card's graceful-degradation path, and the compact dense row.

## Tests

`flutter_app/test/features/dashboard/dashboard_screen_test.dart` (extended) plus any new component
test files for the dense row / coming-soon card if extracted as standalone widgets.

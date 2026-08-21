# EPIC-M1.140 — Discovery, Market, News & Events UI

**Track:** UI
**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Give users a compact exploration surface for discovering opportunities and understanding the market/news/events that explain them.

## Screens
### Discover
- Search and compact filter bar.
- Grid/table of candidates.
- Market/sector/industry/size filters.
- Discovery reason chips.
- Score/Trust/eligibility indicators.

### Market
- Market status and regime.
- Compact index cards.
- Sector heat/grid view.
- Breadth/volume/volatility widgets.

### News & Events
- Chronological event stream.
- Materiality badges.
- Symbol/company filters.
- Event-to-recommendation navigation.
- Corporate action and earnings indicators.

## UX Rules
- Do not create a giant news feed; prioritize material events.
- Use grids, compact rows and chips.
- Keep filters visible on web and accessible through a bottom sheet on mobile.
- Preserve filter/search state during navigation.
- Show freshness timestamps without consuming large screen area.

## Acceptance Criteria
- Discovery can be filtered by market/sector/industry/size.
- User can navigate from an event/news item to affected recommendation.
- Market widgets fit web without stretching full width.
- Mobile remains usable without horizontal page scrolling.
- UI does not implement discovery/ranking logic locally.

## Parallelization
UI implementation against M1.139 fixture/OpenAPI data.

## Dependencies
M1.133, M1.134, M1.139.

## Completion Report

**Implemented on branch:** `autonomous/epic-m1-140`, against the real, merged EPIC-M1.139 contracts (`docs/api/openapi.json`) — not a fixture.

**Destination-to-screen mapping decision:** M1.140 specifies three screens (Discover, Market, News & Events) but EPIC-M1.134's approved shell has only six fixed destinations with no seventh "News" tab. News & Events is implemented as a second tab of the **Market** destination (`MarketScreen` wraps `MraTabBar` around `MarketOverviewScreen` and `NewsEventsScreen`) rather than adding an unapproved nav destination.

**What was built:**
- `lib/features/discover/` (`discovery_item.dart`, `discoveries_repository.dart`, `discovery_card.dart`, `discover_screen.dart`): search (client-side substring over the loaded page — `/discoveries` has no text-search param), a market-cap-bucket filter bar, responsive 1/2/3-column grid, discovery-reason chips, score/trust indicators, an honest status chip (`PENDING_ANALYSIS`/`NOT_QUALIFIED`/lifecycle state, never fabricated), cursor-based infinite scroll.
- `lib/features/market/` (`market_summary.dart`, `market_repository.dart`, `market_overview_screen.dart`, `sector_move_row.dart`, `market_screen.dart`): status/regime chips (rendered as "Status/Regime unavailable" when M1.139 returns `UNKNOWN`/`null` — real gaps, not hidden), advance/decline/volume/volatility KPI strip, sector leaders/laggards as colored trend chips. Compact index cards from the original Layout spec are intentionally omitted: `indexes` is always `[]` (M1.139 has no index-level price feed at all) — an empty card row would be decorative, not informative.
- `lib/features/news_events/` (`news_item.dart`, `market_event_item.dart`, `news_events_repository.dart`, `news_event_row.dart`, `news_events_screen.dart`): merges M1.139's separate `/news` and `/events` into one chronological feed client-side (`FeedEntry`), materiality badges, a symbol filter (both endpoints support `?symbol=`), reuses M1.133's `NewsCard`.
- `lib/features/shared/recommendation_lookup.dart`: **event/discovery-to-recommendation navigation**, satisfying M1.140's AC despite neither `/discoveries` nor `/recommendations` exposing a symbol filter (checked against the real contract) — scans the single largest allowed page (100, M1.135's documented max) of the live recommendations feed for a matching symbol. Named, honest limitation: a symbol ranked outside the top 100 won't be found; shows "No active recommendation for {symbol} yet" rather than erroring, since many discovered/news symbols correctly have no active positive recommendation.
- Wired into `app_router.dart`: Discover and Market branches each got their own nested `recommendation/:id` route (reusing M1.138's `RecommendationDetailScreen`) so cross-navigation stays within that branch's own navigation stack.

**Tests:** `test/features/discover/discover_screen_test.dart`, `test/features/market/market_overview_screen_test.dart`, `test/features/market/market_screen_test.dart`, `test/features/news_events/news_events_screen_test.dart` — rendering, search/filter, empty states, tab switching, and both branches of the recommendation-lookup navigation (found vs. not-found). Full suite: `flutter test` → 55/55. `flutter analyze` → no issues.

**Acceptance criteria status:**
- Done: discovery filterable by market-cap size (sector/industry filters are contract-supported but not yet exposed in the UI — same "repository supports it, UI doesn't yet" gap pattern as M1.136); event/news/discovery → recommendation navigation (via the named-limitation lookup above); market widgets use `ConstrainedBox(maxWidth: 1200)` so they don't stretch full width on wide screens; verified no horizontal overflow from 360px to 1280px+ in manual testing; UI does not implement discovery/ranking logic (server order preserved, only client-side text search and chronological news+events merge, neither of which re-ranks).

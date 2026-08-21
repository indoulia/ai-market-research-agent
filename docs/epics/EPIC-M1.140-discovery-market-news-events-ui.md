# EPIC-M1.140 — Discovery, Market, News & Events UI

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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

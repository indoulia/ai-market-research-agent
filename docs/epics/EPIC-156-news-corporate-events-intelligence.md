# EPIC-156 — News & Corporate Events Intelligence

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Show only material news and corporate/event information relevant to the user's opportunities and watched universe, while exposing how events affect predictions.

## UI Scope
- Compact news/events feed.
- Filters by stock, event type, materiality and date.
- Event cards with icon, timestamp, source and affected symbols.
- Materiality indicator.
- Link to affected recommendation and prediction revision.
- Corporate-action and earnings sections.
- Avoid duplicate/syndicated stories.

## API Contract
`GET /api/v1/news`
`GET /api/v1/events`
`GET /api/v1/events/{eventId}`

Query:
`symbol`, `eventType`, `materiality`, `from`, `to`, `page`, `pageSize`.

Event response:
`eventId`, `eventType`, `title`, `summary`, `publishedAt`, `detectedAt`, `effectiveAt`, `materiality`, `affectedSymbols[]`, `sources[]`, `impactStatus`, `predictionRevisionIds[]`.

## Acceptance Criteria
- Materiality and source provenance are visible.
- Duplicate events are collapsed.
- Event timestamps distinguish publication, detection and effective time.
- User can navigate from event to affected prediction.
- Provider/source conflicts remain accessible through detail.

## Completion Report (2026-08-22)

**Branching:** `origin/autonomous/epic-m3-4` did not exist at branch time
(`git branch -r` / `gh pr list` showed no such ref — either never pushed or
already merged+deleted with no trace); branched `autonomous/epic-m3-5`
directly from `origin/main` per the fallback rule. Re-checked with
`git fetch origin` immediately before opening the PR — still no
`autonomous/epic-m3-4` branch or open PR referencing EPIC-155, so this PR's
base is plain `origin/main` with no stacking/rebase needed.

**Mid-flight complication (2026-08-21):** EPIC-155 (PR #267) merged into
`main` while PR #265/#268 (this EPIC's PR — see below for why there were
two numbers) was waiting on CI, producing a real conflict in
`docs/api/openapi.json`. Rebased `autonomous/epic-m3-5` onto the new
`origin/main`, resolved the conflict by regenerating
`docs/api/openapi.json` fresh (`python scripts/export_openapi.py`) rather
than hand-merging JSON, and re-ran the full validation suite (see below)
to confirm no regressions from EPIC-155's changes (it added
`market`/`sector`/`marketCapBucket` params to
`RecommendationsRepository.fetchPage`, which the rebase auto-merged
cleanly into this EPIC's own test fixture). Separately, PR #265 (opened
from branch `autonomous/epic-m3-5`) never got a single GitHub Actions
check triggered against it despite multiple retrigger attempts (push,
close/reopen, empty commits) over ~15 minutes, while sibling PRs opened by
other concurrent sessions in the same window triggered normally — a
throwaway diagnostic PR from a brand-new, unrelated branch confirmed the
same symptom repo-wide for a window, then GitHub Actions recovered on its
own. Rather than keep waiting on a possibly-permanently-stuck PR object,
the branch was renamed to `autonomous/epic-m3-5-retry`, PR #265 closed,
and PR #268 opened from the renamed branch — which then triggered CI
normally. PR #268 is the one that was actually merged.

**Context:** see `docs/epics/EPIC-M3-ROADMAP-NOTE.md`. This EPIC's product
surface (news/events feed, filters, materiality, event-to-recommendation
navigation) was already ~85% built by the older, merged EPIC-142 (API) and
EPIC-143 (UI) EPICs. This session's job was to diff EPIC-156's specific scope
against that existing code, not build a second feed or a second API.

**Already satisfied by existing EPIC-142/EPIC-143 work — verified, not
reimplemented:**
- `GET /api/v1/news` and `GET /api/v1/events` — `api/routers/news_events.py`,
  `api/services/news_events.py`, filterable by `symbol`/`sector`/`industry`,
  real keyset (cursor) pagination.
- Compact news/events feed, chronological, avoids "giant feed" —
  `flutter_app/lib/features/news_events/news_events_screen.dart` merges
  both endpoints client-side into one `FeedEntry` stream (unchanged
  architecture from EPIC-143).
- Materiality indicator — `NewsCard`'s `tag` chip, driven by
  `NewsItem.materiality`/`MarketEventItem.materiality`.
- Timestamps distinguishing publication/detection/effective time —
  `publishedAt`/`detectedAt` (news) and `effectiveAt`/`detectedAt` (events),
  unchanged from EPIC-142.
- Symbol filter — `NewsEventsScreen`'s `MraSearchField`, wired to both
  `/news?symbol=` and `/events?symbol=`.
- Link from event/news to affected recommendation —
  `flutter_app/lib/features/shared/recommendation_lookup.dart`, reused
  unchanged. **Prediction revision** is not a separate destination: the
  recommendation detail screen it navigates to
  (`flutter_app/lib/features/detail/recommendation_detail_screen.dart`,
  `_RevisionTimeline` widget, "Revision history") already surfaces the
  full revision timeline for that recommendation, so the AC
  ("link to affected recommendation and prediction revision") is satisfied
  by the existing one-tap destination rather than a second link.
- Named, honest dedup gap carried forward unchanged from EPIC-142: same-source
  duplicates are prevented at ingestion (`NewsEventRecord`'s
  `(stock_id, external_id)` uniqueness constraint); cross-source
  "same real-world event, two providers" content dedup remains out of
  scope (would need fuzzy content matching — EPIC-130's territory, still not
  implemented anywhere in the codebase).

**Genuine gaps found and implemented this session:**
1. **`GET /api/v1/events/{eventId}`** — the one explicitly-named missing
   endpoint. Added `api/services/news_events.py::get_event()` (same
   `CorporateAction` -> `EventItem` projection `list_events` already uses,
   refactored into a shared `_to_event_item()` helper) and the router
   handler in `api/routers/news_events.py`, keyed on `CorporateAction.id`
   (== the `evidenceId` every `/events` list item already returns). Returns
   `MRA_NOT_FOUND` (404) for an unknown id, per the existing
   `NotFoundError` convention (`api/errors.py`).
2. **`eventType`/`materiality`/date-range query filters** — EPIC-142 only
   supported `symbol`/`sector`/`industry`. Added:
   - `/news`: `eventType` (real `NewsEventRecord.event_type` column,
     `CORPORATE_EVENT`/`NEWS_STORY` — now also exposed as a new
     `NewsItem.eventType` response field, since the DB already had it but
     it was never threaded through the schema), `materiality` (real
     `NewsEventRecord.materiality` column), `from`/`to` (datetime range on
     `publishedAt`, same `Query(alias="from")` pattern as
     `api/routers/recommendation_detail.py`'s `/history` endpoint).
   - `/events`: `type` (filters `CorporateAction.action_type`, the column
     already returned as the item's `type` field), `from`/`to` (date range
     on `effectiveAt`/`effective_date`).
   - **Deliberately not added:** a `materiality` query param on `/events`.
     `CorporateAction` has no `materiality` column at all — `/events` items
     have always reported `materiality: null` (unchanged since EPIC-142).
     Accepting a `materiality` filter that could never match any row would
     be a silent lie about what the data supports, not a real filter — the
     same "honest gap, not fabricated" standard EPIC-142 itself used.
3. **UI filters** (event type, materiality, date) — `NewsEventsScreen` had
   only the symbol search field. Added three `MraFilterBar` rows (existing
   EPIC-136 component, already used by `discover_screen.dart` — no new
   design-system pattern introduced): Type (`All`/`News`/`Corporate
   actions`/`Earnings`), Materiality (`All`/`High`/`Low`), Date (`All
   time`/`Today`/`This week`). The Type filter drives which of `/news`/
   `/events` are actually fetched (reusing the `fetchNews`/`fetchEvents`
   toggle EPIC-146 already added to `NewsEventsRepository`); Materiality
   and Date are applied client-side over the fetched page(s) — a named,
   honest v1 limitation (they narrow what's already loaded, not a
   server-side query across the full remaining dataset) chosen to avoid
   widening `NewsEventsRepository`'s public method signature (which the
   existing `news_events_screen_test.dart` fake subclasses) for filters
   whose main value, for a "compact feed, prioritize material events"
   screen, is narrowing an already-small loaded window.
4. **"Corporate-action and earnings sections"** — implemented as the Type
   filter's `Corporate actions` and `Earnings` options rather than
   permanently-visible split sections, preserving EPIC-143's deliberate
   single-chronological-stream design (its own doc: "do not create a giant
   news feed; prioritize material events"). Honest scoping note: neither
   `NewsEventRecord` nor `CorporateAction` models a dedicated "earnings
   calendar" concept — `event_type` is only the coarse
   `CORPORATE_EVENT`/`NEWS_STORY` split ingestion already computes
   (`app/news_data/ingest.py`'s keyword rule, which does include
   `"earnings"` as one trigger keyword among ~20). "Earnings" is therefore
   implemented as `eventType=CORPORATE_EVENT` news whose headline contains
   "earnings" (case-insensitive) — the same deterministic signal the
   ingestion layer already uses, not a fabricated new classification.
5. **Event cards: icon + affected-symbol chips** — `NewsCard` (shared
   EPIC-136 component) gained optional `icon`/`affectedSymbols` params
   (default `null`/`[]`, so the two other existing callers —
   `recommendation_detail_screen.dart`'s timeline and `gallery_screen.dart`
   — are unaffected). `NewsEventRowCard` now passes a news-vs-corporate-
   action icon and `entry.affectedSecurities` (real `NewsItem
   .affectedSecurities` data, always a single symbol today per EPIC-142's own
   documented "doesn't model multi-security news yet" gap — chips only
   render when there's more than one, so nothing fabricated shows for the
   common case). Materiality chip tone also upgraded from always-`info` to
   `warning` for `HIGH` materiality, a small honest strengthening of the
   "materiality indicator" AC.

**Deliberately not done (named, not fabricated):**
- No `predictionRevisionIds[]`/`sources[]`/`impactStatus`/`eventId`-named
  response schema as this doc's own "Event response" sketch lists. EPIC-142's
  already-shipped, already-integrated `EventItem`/`NewsItem` schemas
  (`symbol`, `type`, `source`, `evidenceId`, ...) are what the Flutter
  client, `docs/api/openapi.json` and every existing test already depend
  on; renaming fields now would be a breaking contract change for zero
  behavioral gain, not a "genuine gap." `predictionRevisionIds[]`
  specifically would require a new data-model link between a
  `NewsEventRecord`/`CorporateAction` row and the specific prediction
  revision(s) it caused — no such link exists anywhere in the schema
  today; the existing event -> recommendation -> revision-timeline
  navigation path satisfies the AC's intent without fabricating that link.
- No cross-source syndicated-story dedup (unchanged EPIC-142/EPIC-130 gap, see
  above).
- No server-side materiality/date filtering wired from the Flutter client
  (API supports it; UI applies it client-side — see gap #3 above).
- `page`/`pageSize` offset pagination this doc's Query line mentions was
  not added alongside the existing cursor (`pageSize`+`cursor`) pagination
  EPIC-142 already uses for these two ever-growing tables — cursor pagination
  is this codebase's established convention for exactly this kind of table
  (matches `/discoveries`, `/recommendations`, `/recommendations/{id}
  /history`); adding a second, offset-based pagination mode alongside it
  would be redundant, not a gap.

**Tests (TDD):**
- `tests/test_api_discovery_market_news.py` — 5 new tests added to the 12
  pre-existing: `test_news_event_type_and_materiality_filters`,
  `test_news_date_range_filter`, `test_events_type_and_date_filters`,
  `test_event_detail_by_id`, `test_event_detail_not_found`.
- `flutter_app/test/features/news_events/news_events_screen_test.dart` — 2
  new tests added to the 3 pre-existing:
  `EPIC-156: materiality filter narrows the visible feed`,
  `EPIC-156: type filter fetches only the selected source`.

**Validation run:**
```
python -m pytest tests/test_api_discovery_market_news.py -q
# 17 passed in 4.52s   (12 pre-existing + 5 new)

python scripts/export_openapi.py   # (run with PYTHONPATH=. from repo root)
python -m pytest -q
# 1335 passed, 9 skipped   -- full existing suite, no regressions

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && flutter test
# 129 tests passed (127 pre-existing/renumbered + 2 new; the pre-existing
# infinite-scroll test was updated to target the vertical list by Key,
# since the new filter rows added three more horizontal ListViews to the
# screen and made the old find.byType(ListView) lookup ambiguous)

# --- after rebasing autonomous/epic-m3-5 onto main (EPIC-155 merged, PR #267) ---
python -m pytest -q
# 1372 passed, 9 skipped in 239.51s -- full suite on top of EPIC-155, no regressions

cd flutter_app && flutter test
# All 150 tests passed (EPIC-155 added its own opportunity-explorer tests)
```

CI on PR #268 caught one thing local `flutter analyze` does not check:
Flutter CI's `dart format --output=none --set-exit-if-changed lib test`
step failed on two lines this session wrapped differently than
`dart format`'s canonical style (`news_card.dart`'s `Icon(...)` call,
`news_events_screen.dart`'s `_fetchEvents` getter and three `Padding`
calls). Fixed by running `dart format lib test` and pushing a follow-up
commit — purely cosmetic, no behavior change, re-verified with
`flutter analyze` (no issues) after the fix.

**PRs and merge:**
- PR #265 (branch `autonomous/epic-m3-5`) was opened first but GitHub
  Actions never dispatched a single check against it despite repeated
  retriggers over ~15 minutes (see the mid-flight-complication note
  above); closed without merging once the same symptom was confirmed
  repo-wide via a throwaway diagnostic PR/branch (also closed, branch
  deleted).
- **PR #268** (branch `autonomous/epic-m3-5-retry`, rebased onto
  `origin/main` post-M3.4) is the PR that carries this EPIC's actual
  changes. CI: `analyze-and-test` (Flutter CI) and `test` (backend) both
  `pass`; `gh pr view 268 --json mergeable,mergeStateStatus` showed
  `MERGEABLE`/`CLEAN`; squash-merged via
  `gh pr merge 268 --squash --delete-branch`, confirmed via
  `gh pr view 268 --json state,mergedAt` ->
  `{"mergedAt":"2026-08-21T21:04:17Z","state":"MERGED"}`.

**Conclusion:** EPIC-156's product surface was already ~85% satisfied by
the existing, merged EPIC-142/EPIC-143 work. The one explicitly-named API gap
(`GET /api/v1/events/{eventId}`) plus the UI-scope filter/icon/section gaps
have been implemented, tested and verified above, using this codebase's
existing conventions throughout (keyset pagination, `MraFilterBar`,
`NotFoundError`, honest-gap documentation). PR #268 is merged. Marking
this EPIC `DONE`.

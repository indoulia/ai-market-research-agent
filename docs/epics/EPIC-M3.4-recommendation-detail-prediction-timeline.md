# EPIC-M3.4 — Recommendation Detail & Prediction Timeline

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Provide a compact but complete view of a recommendation's current prediction, evidence, revisions, target/SL/horizon and outcome history.

## UI Scope
- Header with symbol, price, positive recommendation state and freshness.
- Metric grid: horizon, target, SL, upside, score, probability/confidence, Trust and uncertainty.
- Price/target/SL chart.
- Fundamental, technical, market, news and event evidence sections.
- Why MRA selected this opportunity.
- What changed since previous prediction.
- Prediction-version timeline with timestamps and reasons.
- Active/outcome status.
- Feedback action.
- Progressive disclosure so detail remains uncluttered.

## API Contract
`GET /api/v1/recommendations/{recommendationId}`
`GET /api/v1/recommendations/{recommendationId}/timeline`
`GET /api/v1/recommendations/{recommendationId}/evidence`
`GET /api/v1/recommendations/{recommendationId}/outcome`

Recommendation detail must include:
- immutable prediction version identifier
- current values
- `createdAt`, `updatedAt`, `asOf`
- evidence references
- provider/source provenance
- model/configuration versions
- lifecycle state

Timeline returns ordered immutable revisions with change reason and affected metrics.

## Acceptance Criteria
- Historical revisions cannot be overwritten.
- User can reconstruct why target/SL/confidence/Trust changed.
- Evidence is linked to source and timestamp.
- Target/SL/outcome states are consistent with M1.119.
- UI remains usable on mobile and desktop.

## Completion Report (2026-08-22)

**Branching context:** `origin/autonomous/epic-m3-3` existed (PR #260,
open/unmerged) when this branch (`autonomous/epic-m3-4`) was created, so
per the product owner's standing branching instruction it was stacked on
top of it instead of `origin/main`. Re-checked immediately before opening
the PR: PR #260 (and #261, EPIC-M3.2) were both still open. This EPIC's
scope does not depend on either — it only touches `/api/v1/recommendations/*`
and `flutter_app/lib/features/detail/*`, neither of which M3.2/M3.3 modify —
so no blocking dependency exists in practice. `git rebase --onto origin/main
origin/autonomous/epic-m3-3 HEAD` was run right before opening the PR to
strip M3.3's own commits back out, leaving only this EPIC's changes
(verified with `git diff origin/main...HEAD` / `git log --oneline
origin/main..HEAD`).

**Context:** per `docs/epics/EPIC-M3-ROADMAP-NOTE.md`, this EPIC's number
was renumbered from a collision with the older split track's own
`M1.135-recommendation-detail-prediction-timeline.md`. The real, substantive
overlap is with **`EPIC-M1.137` (Recommendation Detail, Revision & History
API, `DONE`, merged PR #166) and `EPIC-M1.138` (Recommendation Detail &
Longitudinal History UI, `DONE`)** — both already implement almost
everything this EPIC's UI Scope and API Contract ask for. This session's
job was to diff M3.4's specific scope against that existing, merged code,
not to build a second, parallel screen or API.

**Already satisfied by existing M1.137/M1.138 work — verified, reused,
not reimplemented:**
- `GET /api/v1/recommendations/{recommendationId}` — `api/routers/recommendation_detail.py`,
  `api/services/recommendation_detail.py::get_detail`. Full field shape
  (immutable `predictionVersion`, `createdAt`/`updatedAt`/`asOf`, current
  target/SL/horizon/upside/probability/score/confidence/trustScore/
  uncertainty/evidenceStrength, evidence summaries, provider provenance,
  liquidity, lifecycle `status`) already matches this EPIC's own "Detail
  Response must include" list field-for-field.
- `GET /api/v1/recommendations/{recommendationId}/outcome` — unchanged,
  already exact (`status`/`detectedAt`/`observedPrice`/`realizedReturnPct`/
  `targetHit`/`stopLossHit`/`horizonExpired`/`benchmarkReturnPct`/`evidenceId`).
- Header, metric grid (horizon/target/SL/upside/score/confidence/trust),
  price/target/SL chart, fundamental/technical/market/news/event evidence
  sections, outcome section, feedback action —
  `flutter_app/lib/features/detail/recommendation_detail_screen.dart`
  (M1.138) already built all of these against M1.137's contracts.
- Feedback action — `flutter_app/lib/features/feedback/recommendation_feedback_section.dart`
  and `POST /recommendations/{id}/feedback` (`api/services/feedback.py`),
  pre-existing and unmodified, already wired into the detail screen.
- Immutability of historical revisions — `app/recommendation_revision.py`'s
  `RecommendationRevisionImmutableError` guard (M1.55), unchanged; this
  EPIC's new `/timeline` endpoint reads that same immutable chain, never
  writes to it.

**Genuine gaps found and implemented this session:**

*API* (`api/schemas/recommendation_detail.py`, `api/services/recommendation_detail.py`,
`api/routers/recommendation_detail.py`):
- `GET /api/v1/recommendations/{recommendationId}/timeline` — did not
  exist under any name. M1.137's `/history` is revisions-only (a
  `RecommendationRevision` row never exists for the original prediction),
  so it cannot reconstruct the *whole* lifecycle in one call. The new
  `TimelineItem`/`get_timeline` always starts with version 1 (the
  original prediction, `reason: "INITIAL_PREDICTION"`), followed by every
  immutable revision in order, each carrying a new `affectedMetrics: list[str]`
  field (`_affected_metrics`, derived from `compare_versions`' own deltas
  plus a trust-score comparison) — directly satisfying the AC "user can
  reconstruct why target/SL/confidence/Trust changed" without the client
  re-deriving anything. Small and bounded (a recommendation is rarely
  revised more than a handful of times), so unlike `/history`/`/events`
  this is not cursor-paginated — the full ordered list is always returned.
- `GET /api/v1/recommendations/{recommendationId}/evidence` — did not
  exist as its own endpoint (evidence was only ever embedded in
  `/{id}`'s detail payload). Following the same precedent as EPIC-M3.1
  (which added standalone `/version`/`/capabilities` even though
  `/app/bootstrap` already had that data combined, because the epic
  "explicitly calls out" its own representative endpoints), added a thin
  `get_evidence` that delegates to `get_detail` and projects the
  evidence/provenance subset (`fundamental`/`technical`/`market`/`news`/
  `events`/`evidenceStrength`/`liquidity`/`providerEvidence`) into a new
  `EvidenceResponse` — always exactly consistent with the detail
  endpoint, never a second independently-computed source of truth.
- `RecommendationDetail.evidenceFreshness` — new field on the detail
  schema (`evidence_freshness(session, active.id)`, the same
  `context_summaries.evidence_freshness` helper `/recommendations` and
  `/opportunities`' `RecommendationSummary.evidenceFreshness` already use,
  EPIC-M1.144). M1.137's detail response never exposed this, even though
  this EPIC's own UI Scope explicitly asks for header "freshness".
- `docs/api/openapi.json` regenerated (`python scripts/export_openapi.py`).

*UI* (`flutter_app/lib/features/detail/`):
- `timeline_item.dart` (new) — `RecommendationTimelineItem` model parsed
  from the new `/timeline` contract; `recommendation_detail_repository.dart::fetchTimeline`
  added alongside the existing `fetchHistory`/`fetchEvents`/`fetchOutcome`
  (the latter three unchanged, still real, working contracts — `fetchHistory`
  is simply no longer this *screen's* data source, not removed).
- `recommendation_detail_screen.dart` — the screen now fetches `/timeline`
  instead of `/history` (a strict superset: same revision data, plus the
  original version, plus reasons/affected metrics), and:
  - Header now shows a "Stale evidence" badge when `evidenceFreshness ==
    "STALE"`, mirroring `RecommendationCard`'s already-established
    convention (M1.144) of only ever asserting confirmed staleness, never
    fabricating freshness.
  - New `_WhySelectedSection` ("Why MRA selected this opportunity") —
    a short, always-visible narrative synthesized from fields the detail
    endpoint already returns (probability/score/confidence, evidence
    strength, fundamental/technical/market summaries, provider list). No
    new backend field: this platform already expresses "why" as those
    structured summaries: this section's only job is to present them as
    an explicit answer to "why", distinct from the exhaustive evidence
    panel.
  - New `_WhatChangedSection` ("What changed since previous prediction")
    — a prominent, above-the-fold callout reading the latest `/timeline`
    entry's `changeSummary` + `affectedMetrics` chips, honestly stating
    "No revisions yet" when `timeline.length == 1`.
  - The price/target/SL chart and the revision timeline (`_RevisionTimeline`,
    renamed in intent to "prediction-version timeline") now plot/list
    from `_timeline` instead of `_history` — the chart in particular now
    includes the *original* entry price as its first point, which
    `/history` alone could never provide (a real, if minor, chart-accuracy
    fix, not just a rename).
  - Progressive disclosure: new `flutter_app/lib/design_system/components/mra_expandable_section.dart`
    (`MraExpandableSection`, exported from `design_system.dart`) wraps the
    evidence panel, news/events feed and prediction-version timeline —
    each collapsible/expandable in place, defaulting expanded (so no
    existing behavior regresses) while letting the user tuck any of them
    away, satisfying the UI Scope's own "progressive disclosure so detail
    remains uncluttered" line, which M1.138 had not implemented (it only
    used a two-column vs. stacked responsive split, not per-section
    disclosure).

**Tests (TDD):**
- `tests/test_api_recommendation_detail.py` — 7 new tests: detail includes
  a valid `evidenceFreshness`; `/timeline` 404s like every other
  sub-resource; timeline has exactly the original version when never
  revised (`reason == "INITIAL_PREDICTION"`, `affectedMetrics == []`);
  timeline includes both the original and a revision with the right
  `affectedMetrics`; timeline is stable/immutable across repeated fetches;
  `/evidence` 404s and matches the detail endpoint's own evidence fields
  exactly.
- `flutter_app/test/features/detail/recommendation_detail_screen_test.dart`
  — 6 new widget tests: revision timeline now sourced from `/timeline`;
  stale-evidence badge shown only for `"STALE"` and omitted for `"FRESH"`;
  why-selected narrative renders; what-changed shows the honest "no
  revisions yet" state and, separately, a revision's summary + affected
  metric chips; the evidence panel collapses/expands via the new
  progressive-disclosure wrapper.
- `flutter_app/test/e2e/end_to_end_journey_test.dart` — updated to mock
  `/timeline` instead of `/history` (matching the screen's new data
  source) and to include `evidenceFreshness` in the scripted detail
  payload; the full sign-in -> recommendations -> detail -> feedback ->
  preferences journey still passes end to end.

**Validation run:**
```
DATABASE_URL="postgresql+psycopg://ci:ci@localhost/market_agent" python -m pytest -q
# 1354 passed, 9 skipped -- full existing suite plus the 7 new tests, no regressions.

cd flutter_app && flutter test
# All tests passed! (145 tests, incl. the 6 new detail-screen tests and
# the updated end-to-end journey test)

cd flutter_app && flutter analyze
# No issues found!
```

**Deliberately not done (rationale):**
- No second Flutter screen or second API surface — M1.137/M1.138's
  existing screen and contracts were extended in place, per this EPIC's
  own framing as filling the *remaining* gap in an already-largely-built
  product surface.
- `flutter_app/lib/features/detail/history_item.dart` and
  `RecommendationDetailRepository.fetchHistory`/`fetchEvents` were left
  entirely unchanged (still real, tested, working contracts) even though
  this screen no longer calls `fetchHistory` — `/history` remains a valid,
  independently useful contract (e.g. for a future paginated "load more"
  view), so it was not deleted just because this one screen switched to
  the richer `/timeline` for its own needs.
- Benchmark-relative result, true real-time outcome-detection latency and
  trading-day-aware `expiryAt` remain the same named, honest gaps M1.137
  already documented (M1.129/M1.119/M1.121 respectively) — this EPIC
  neither claims nor fabricates progress on them.

**Conclusion:** EPIC-M3.4's scope was already ~85% satisfied by the
existing, merged M1.137/M1.138 work. The concrete, named gaps — a
dedicated `/timeline` endpoint with structured affected-metrics (not just
a revisions-only `/history`), a dedicated `/evidence` endpoint, header
freshness, an explicit "why selected" narrative, an explicit "what
changed" callout, and per-section progressive disclosure — have all been
implemented, tested and verified above. Marking this EPIC `DONE`.

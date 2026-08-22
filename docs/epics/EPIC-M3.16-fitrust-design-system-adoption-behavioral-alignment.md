# EPIC-M3.16 — FiTrust UI/UX Design-System Adoption & Behavioral Alignment

**Status:** DONE (self-approved per standing delegation — see project memory `project_post_epic_deployment_validation`; merged via PR #295, commit `4866ce9`)
**Execution Status:** COMPLETED
**Track:** UI
**Priority:** P1

## Context

This EPIC is the first past the end of the M3.1-M3.15 roadmap (see
`docs/epics/EPIC-M3-ROADMAP-NOTE.md`). "FiTrust" is not a new brand or a
new component library — it is a design *principle*: every screen should
visually and behaviorally read as a credible, conservative financial-
research tool, never as a hype/urgency-driven trading app. The existing
MRA design system (`flutter_app/lib/design_system/`, EPIC-M1.133/M3.13)
already has the tokens and components this needs; M3.13 already audited
accessibility/responsiveness/performance. What has never been audited
end-to-end is (a) whether every screen actually *uses* the shared MRA
tokens/components instead of ad-hoc `Color(0x...)`/raw `Text(style:
TextStyle(...))`/bespoke widgets, and (b) whether the app's *behavior* —
tone of copy, confidence framing, error/empty states, use of urgency
color (red/orange) — consistently avoids overstating certainty or
pressuring action, per the product's own "positive-opportunity, no
trading pressure" constraint.

## Objective

Audit every screen and shared component for (1) design-system token/
component adoption and (2) behavioral consistency with a credible,
non-hype financial-research tone, and fix genuine gaps found — without
introducing a new visual language, a rebrand, or new product features.

## UI Scope

- **Token adoption:** no screen hardcodes a raw color/font-size/spacing
  value where an `MraColors`/`MraSpacing`/`MraTypography` token already
  exists for that role; flag (don't invent new tokens for) any role that
  is genuinely missing.
- **Component reuse:** no screen re-implements a bespoke card/chip/badge/
  empty-state/loading-state that duplicates an existing `Mra*` component.
- **Semantic color discipline:** positive/warning/error/market-state
  colors are only used for their defined semantic meaning (e.g. never use
  `error` red for a merely-informational or "no data yet" state).
- **Certainty framing:** every probability/success-rate/score display
  that has a small sample size shows the existing `smallSample`/low-
  confidence indicator; no screen presents a point estimate as more
  certain than the underlying data supports.
- **Tone/copy consistency:** button/label/empty-state copy across screens
  is calm and descriptive (e.g. "No matching opportunities yet", not
  "You're missing out!"); no urgency, countdown, or FOMO-style language
  anywhere in the app (product constraint: recommendations only, no
  trading pressure).
- **Consistent interaction feedback:** the same class of action (save,
  submit, retry, dismiss) gives the same kind of feedback (toast vs.
  inline vs. dialog) across every screen it appears on, not a different
  pattern per screen.

## Acceptance Criteria

- A written audit trail (this doc's Completion Report) lists every
  screen/component checked and every gap found, each with a file:line
  reference — no unverified/bulk-reported findings.
- Every genuine gap found is fixed by reusing an existing token/component/
  pattern, not by inventing a new one, unless a real missing token is
  identified and named explicitly as a scoped addition.
- `flutter analyze`, `dart format --set-exit-if-changed`, and `flutter
  test` all pass with zero regressions after the fixes.
- No product-constraint violation is introduced or left uncorrected
  (positive-opportunity-only framing, no bearish/sell language, no
  trading-pressure copy).

## Completion Report (2026-08-22)

**Audit method:** a dedicated audit pass (no edits) read
`flutter_app/lib/design_system/design_system.dart` and its token files
(`mra_colors.dart`, `mra_spacing.dart`, `mra_typography.dart`) to establish
the real available tokens/components, then read/grepped every screen
under `flutter_app/lib/features/**`, `flutter_app/lib/app_shell/**`, and
`flutter_app/lib/gallery/gallery_screen.dart` against each of the six UI
Scope bullets. 48 `EdgeInsets.all/symmetric` call sites, all
`Color(0x...)`/`TextStyle(...)`/`Colors.*` literals, all `MraChipTone`
usages, all `smallSample`/`sampleSize`/confidence-field render sites, all
user-facing string literals for hype/urgency/trading-pressure language,
and all `SnackBar`/`MraToast`/`showDialog` feedback call sites were
checked.

### Already compliant, verified — no changes needed

- **Token adoption:** every `EdgeInsets.all/symmetric` in
  `lib/features` other than the two gaps below already uses
  `MraSpacing.*`. No raw `Color(0x...)`, no raw `TextStyle(...)`, no
  `Colors.red/green/orange/amber` literals anywhere in `lib/features`.
- **Component reuse:** no hand-rolled card/badge/skeleton/empty-state
  widget duplicates an existing `Mra*` component; `SectorMoveChip`
  (market) and `_LifecycleChip` (discover) are thin, legitimate
  `MraChip` wrappers, not reimplementations.
- **Certainty framing:** every screen rendering a `smallSample`/
  `sampleSize` field (`dashboard_screen.dart`, `tracking_screen.dart`)
  already shows the flag alongside the value. `discovery_card.dart`/
  `recommendation_detail_screen.dart`'s `ScoreIndicator` usages have no
  `sampleSize`/`smallSample` field to show at all — no such field exists
  anywhere in the discovery/recommendation-detail API models, so this is
  a named, out-of-scope backend gap (would require new API data, not a
  UI-only fix), not silently ignored.
- **Tone/copy:** a broad grep across `lib/features` for hype/urgency/
  FOMO patterns and buy/sell/trade action language found zero user-facing
  matches (two "guarantee" hits are internal code comments, not rendered
  strings). No countdown/expiry copy reads as urgent.
- **Consistent interaction feedback:** only two `showMraToast` call sites
  exist (`discover_screen.dart`, `news_events_screen.dart`), both the same
  action-class (informational nudge on tap). Save/submit feedback
  (`quick_preferences_screen.dart`, `recommendation_feedback_section.dart`)
  both use the same inline-status-text pattern. No `SnackBar`/
  `showDialog` usage exists anywhere in `lib/features`, so there is no
  mixed-pattern gap to fix.

### Genuine gaps found and fixed

1. **Semantic color discipline — `SectorMoveChip` (`flutter_app/lib/features/market/sector_move_row.dart:18`).**
   Was `tone: isUp ? MraChipTone.positive : MraChipTone.error` for a
   sector's average % move. `MraColors`'s own doc comment
   (`mra_colors.dart:44-45`) defines `marketUp`/`marketDown`/`marketFlat`
   specifically "so a market up/down chip never reads as a general
   success/failure signal" — `RecommendationCard` already honors this for
   price-change coloring (`scheme.marketUp`/`marketDown`, not
   `positive`/`error`), but `SectorMoveChip` bypassed it because
   `MraChipTone` had no market-state variant to reach for. Fixed by
   adding `MraChipTone.marketUp`/`marketDown` (mapped to the existing
   `scheme.marketUp`/`marketDown` foregrounds) plus two new, explicitly
   scoped container tokens — `MraColors.marketUpContainer`/
   `marketDownContainer` (`mra_colors.dart`) — since no container tint
   existed yet for market-state chip backgrounds; `SectorMoveChip` now
   uses the new tones. No other `MraChipTone.positive`/`.error` call site
   in the app was a market-direction case (verified: `active_prediction_card.dart`'s
   target-hit/stop-loss, `recommendation_detail_screen.dart`'s
   upside%/target-hit/stop-loss, `system_health_screen.dart`'s
   OK/DEGRADED/OUTAGE, `learning_screen.dart`'s verdict, `discovery_card.dart`/
   `discovery_pipeline_panel.dart`'s stage/verdict, and
   `opportunity_explorer_screen.dart`'s freshness are all genuine
   success/failure/status semantics, not market direction — left
   unchanged).
2. **Semantic color discipline — `ScoreIndicator` (`flutter_app/lib/design_system/components/score_indicator.dart:34-39`).**
   Mapped any score/confidence/trust value below 40 to `scheme.error`
   (alarm red). Every call site (`recommendation_card.dart`,
   `discovery_card.dart`, `recommendation_detail_screen.dart`) renders
   this only for an already-surfaced, positive-population opportunity —
   the platform's own product constraint is that a stock failing
   criteria goes to backlog and is never shown as a recommendation at
   all, so a low score/confidence/trust value here is a weaker positive
   signal, never a failure/error condition. Presenting it in alarm red
   overstates negativity the product constraint forbids. Fixed by
   removing the `error` branch entirely — the indicator now uses
   `positive` (>=70) or `warning` (<70), both pre-existing tokens; no new
   color introduced.
3. **Token adoption — `flutter_app/lib/features/dashboard/dashboard_screen.dart`.**
   Two magic-number spacing values duplicating an existing token's exact
   role: the sector-search field's `contentPadding` used
   `horizontal: 12` (now `MraSpacing.md`), and `_RecentChangesCard`'s
   per-row `Padding` used `vertical: 2` with no matching token (now
   `MraSpacing.xs`, the nearest real token, a 2px increase in row
   spacing — accepted as the correct fix per this EPIC's own AC: reuse an
   existing token rather than inventing a new one).
   A third candidate — the same search field's `borderRadius:
   BorderRadius.circular(12)` — was checked and left unchanged: the
   nearest token, `MraRadii.md`, is `10`, a different value, so replacing
   it would be a visual change disguised as a token-adoption fix, not a
   like-for-like substitution; not a genuine duplicate.

### Deliberately not done (rationale)

- **No new `MraChipTone.marketFlat`** — `SectorMoveChip`'s
  `averageChangePct` is rendered as a strict up/down binary (`isUp =
  averageChangePct >= 0`); there is no third "flat" branch in this widget
  to wire it to, so adding an unused enum value/token pair would be
  speculative, not a fix for an observed gap.
- **No small-sample indicator added to `ScoreIndicator`** — see
  "Already compliant" above; the underlying `sampleSize` field doesn't
  exist in the discovery/recommendation-detail API models. Naming this
  as a real, out-of-scope gap rather than fabricating a UI-only
  workaround.
- **Gallery updated for completeness, not because it was a named gap:**
  `flutter_app/lib/gallery/gallery_screen.dart`'s Chips section gained
  `Market up`/`Market down` example chips alongside the existing five
  tones, so the component showcase stays accurate now that the enum has
  two more values.

### Tests (TDD)

- `flutter_app/test/features/market/sector_move_row_test.dart` (new) —
  asserts an up move resolves to `MraChipTone.marketUp` and a down move
  to `MraChipTone.marketDown` (would fail against the pre-fix
  `positive`/`error` tones).
- `flutter_app/test/design_system/components_smoke_test.dart` — extended
  the existing "every tone renders its label" `MraChip` test to cover
  the two new tones; added a new `ScoreIndicator` test asserting a low
  (5/100) value's resolved `CircularProgressIndicator` color is
  `MraColors.warning`, explicitly `isNot(MraColors.error)` (would fail
  against the pre-fix error-branch code).

**Validation run:**
```
cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# 148 files; ran clean after formatting the 2 new/changed files

cd flutter_app && flutter test
# 215 tests passed, All tests passed! (was 212 before this EPIC — 3 new tests)
```

No Python/API changes in this EPIC (UI-only scope, per its own Track);
no backend tests run or affected.

### Conclusion

Five of the six UI Scope areas (component reuse, certainty framing,
tone/copy, consistent feedback, and the majority of token adoption) were
already fully compliant — verified by direct audit, not assumed. Three
genuine, narrowly-scoped gaps were found and fixed, all by reusing
existing tokens/patterns except for two explicitly-named new container
tokens (`marketUpContainer`/`marketDownContainer`) required because no
market-state chip background existed yet. No rebrand, no new visual
language, no new product feature. Marking this EPIC `VALIDATING` pending
PR merge.

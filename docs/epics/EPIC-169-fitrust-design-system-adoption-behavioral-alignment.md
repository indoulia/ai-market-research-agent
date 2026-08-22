# EPIC-169 — FiTrust UI/UX Design-System Adoption & Behavioral Alignment

**Status:** DONE (self-approved per standing delegation — see project memory `project_post_epic_deployment_validation`; merged via PR #295, commit `4866ce9`)
**Execution Status:** COMPLETED
**Track:** UI
**Priority:** P1

## Context

This EPIC is the first past the end of the EPIC-152-M3.15 roadmap (see
`docs/epics/EPIC-M3-ROADMAP-NOTE.md`). "FiTrust" is not a new brand or a
new component library — it is a design *principle*: every screen should
visually and behaviorally read as a credible, conservative financial-
research tool, never as a hype/urgency-driven trading app. The existing
MRA design system (`flutter_app/lib/design_system/`, EPIC-136/EPIC-164)
already has the tokens and components this needs; EPIC-164 already audited
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

## Follow-up (2026-08-22) — fonts, buttons, flow deep audit

The first pass above under-scoped the user's actual intent: "Main
purpose of this epic was to use theme fonts, designes, flow, buttons,
widgets etc." — a dimension-by-dimension re-audit dedicated specifically
to typography, buttons, and navigation/interaction flow (folded too
narrowly into "token adoption" and "feedback consistency" the first
time). This follow-up read `mra_typography.dart`/`mra_theme.dart` fully,
then compared call sites *across screens* for each of the four
categories side by side, rather than checking one screen at a time in
isolation.

### Findings

1. **Typography — card-header type-scale mismatch.**
   `flutter_app/lib/features/dashboard/dashboard_screen.dart`'s
   `_RecentChangesCard` header used `theme.textTheme.titleSmall`, while
   the functionally identical "compact card header above a short item
   list" role uses `titleMedium` everywhere else it appears
   (`market_overview_screen.dart`'s "Sector leaders"/"Sector laggards",
   `tracking_trend_card.dart`). Fixed: now `titleMedium`.
2. **Buttons — retry action used a different button type per screen.**
   The shared `MraStateView.error` (`state_views.dart`) renders its
   retry action as a `FilledButton`, but
   `general_settings_screen.dart`'s display-preferences error case
   hand-rolled its own error layout with an `OutlinedButton` for the
   identical "Retry" action instead of using `MraStateView.error` at
   all — a widget-reuse gap and a button-type gap at once. Fixed: the
   hand-rolled `Column` (two `Text`s + `OutlinedButton`) is now
   `MraStateView.error(title: ..., message: ..., onAction: _load)`,
   matching every other screen with an error state
   (market_overview/learning/discover/tracking/feedback_history/
   quick_preferences/dashboard/system_health/recommendation_detail/
   opportunity_explorer/news_events all already used it — this was the
   sole hand-rolled exception).
3. **Buttons — "Load more" used three different treatments for the
   same interaction.** `dashboard_screen.dart` used `TextButton`;
   `feedback_history_screen.dart`, `system_health_screen.dart`, and
   `tracking_screen.dart` (two sites) all use `OutlinedButton` for the
   literal same "Load more" action. Fixed: `dashboard_screen.dart` now
   uses `OutlinedButton`, matching the majority (4 existing sites).
4. **Flow — genuinely consistent, verified by cross-screen comparison,
   no fix needed.** Every "view recommendation detail" tap across 5+
   screens uses `context.push` to a route; every filter/sort selection
   uses `showMraBottomSheet`; zero `showDialog(` call sites exist
   anywhere in the app, and no destructive/irreversible action exists
   in this product's scope that would need one (sign-out ends a
   session, not data; filters/chips are reversible).

### Deliberately not done (rationale)

- **"Load more" vs. silent scroll-triggered auto-load** — three screens
  (`opportunity_explorer_screen.dart`, `discover_screen.dart`,
  `news_events_screen.dart`) auto-load on scroll with no visible button
  at all, a genuinely different pagination UX from the explicit-button
  screens above. Unifying these two paradigms into one is a real
  product/UX decision (which pattern should win, for which list
  lengths), not a token-consistency fix — named here as a real,
  deliberately out-of-scope gap for a future EPIC to decide, not
  silently changed.
- **No global `ElevatedButtonThemeData`/`OutlinedButtonThemeData`
  added to `mra_theme.dart`** — every button in the app already runs on
  Material 3's own consistent defaults (verified: no screen passes an
  inline `ButtonStyle`/`styleFrom` override), so there was no actual
  divergent styling to centralize; the two real gaps above were about
  *which* button type/component was chosen per action-class, not about
  missing shared styling.

### Tests (TDD)

- `flutter_app/test/features/dashboard/dashboard_screen_test.dart` —
  extended `'renders the recently-changed widget'` to assert the header
  `Text`'s style equals `theme.textTheme.titleMedium`; extended the
  "Load more opportunities" test to assert the button is an
  `OutlinedButton` ancestor, not just that the label text exists.
- `flutter_app/test/features/preferences/general_settings_screen_test.dart`
  (new test) — a `_FailOnceRepository` drives the error path; asserts
  `FilledButton` (via `MraStateView.error`) renders with the "Retry"
  label and that tapping it recovers to the loaded state.

**Validation run:**
```
cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# clean after formatting the 1 changed test file

cd flutter_app && flutter test
# 216 tests passed, All tests passed! (was 215 after the first M3.16 pass)
```

### Conclusion

3 additional genuine gaps found and fixed across typography and button
consistency; flow was audited cross-screen and found genuinely
consistent. One real gap (load-more button vs. auto-load-on-scroll
paradigm split) is named as deliberately out of this EPIC's safe-to-fix
scope, not silently ignored. Re-confirming `DONE` after this follow-up.

## Follow-up (2026-08-22) — brand color fidelity & a missed reuse gap

User feedback after EPIC-170 (Marksy brand identity) shipped: the app
still didn't look aligned with this EPIC's own FiTrust precedent —
"buttons, big filters... not fully aligned." Audit method this time:
live-screenshotted the actual Rancher-deployed build
(`http://market-agent.test/`, pod created after EPIC-170's merge) via a
headless-Chromium Playwright script rather than reading code in
isolation, since the prior two passes' code-only review had already
covered token/typography/button-type consistency and this complaint was
about something neither pass had checked — how the app actually renders.

### Findings

1. **Buttons/links/selected-nav render a muted color, not the real
   Marksy blue.** Screenshotting the sign-in screen showed the
   "Continue" `FilledButton` as a grayish slate-blue, not
   `MraColors.brandPrimary` (`#2563EB`) visible in the logo right next
   to it. Root cause: `mra_theme.dart`'s `ColorScheme.fromSeed(seedColor:
   MraColors.brandPrimary)` — Material 3's tonal-palette algorithm
   derives `colorScheme.primary` at a fixed tone from the seed's hue,
   which visibly diverges from the literal hex it started from. EPIC-170
   itself claimed brandPrimary "cascad[es] through `ColorScheme.fromSeed`
   to `colorScheme.primary`" — true mechanically, false visually. Compounding
   this: EPIC-170 also added `brandPrimaryLight`/`brandDeepNavy`/
   `brandHighlight` tokens "for direct use" that were never actually
   wired anywhere (verified: zero non-declaration references before this
   fix) — dead tokens, and no dark-theme-appropriate primary existed at
   all. Fixed in `mra_theme.dart`: keep `ColorScheme.fromSeed` for every
   other role (secondary/tertiary/surfaces stay in Material's tonal
   harmony), but pin `primary`/`onPrimary` explicitly — light theme to
   `brandPrimary`/`neutral0`, dark theme to the previously-dead
   `brandPrimaryLight`/`brandDeepNavy` (now actually used). Confirmed
   visually by rebuilding `flutter build web` and re-screenshotting: the
   button now matches the logo exactly.
2. **Dashboard's sector filter duplicates `MraSearchField` instead of
   reusing it** (`dashboard_screen.dart`'s `_buildHeader`). This EPIC's
   own first pass (finding 3, above) already fixed two magic-number
   spacing values in this exact `TextField` without noticing the whole
   widget hand-copies `design_system/components/mra_search_field.dart`
   — the identical filled/isDense/borderRadius-12/surfaceContainerHigh
   shared component `discover_screen.dart` already uses one screen over
   for its own search field. A genuine component-reuse gap missed twice.
   Fixed: extended `MraSearchField` with optional `prefixIcon` (default
   `Icons.search`, so Discover's call site is unaffected) and
   `onSubmitted`, then switched `dashboard_screen.dart` to it, removing
   ~30 duplicated lines.

### Deliberately not done (rationale)

- **Did not override `primaryContainer`/`secondary`/`tertiary`.** Only
  `primary`/`onPrimary` were the reported/observed problem (buttons,
  links, selected-nav icon); widening the override to roles no one
  flagged risks a contrast regression nobody asked for.
- **Did not resize `MraSearchField`/the Dashboard or Discover search
  bar.** The live screenshots show both as full-width, ~48px filled
  boxes above the compact chip filter rows — visually prominent by
  design (search bars are conventionally full-width), and Discover's
  identical-styled field is the *reference* pattern, not a bug. The
  actual, verified gap was Dashboard silently duplicating that pattern
  instead of importing it, not its size.
- **Did not change the app shell header or navigation rail/bottom nav.**
  Live-screenshotted Home, Discover and Tracking side by side: the top
  bar (logo + search + account icons) and left nav rail render
  consistently across every destination with correct selection state on
  every screen checked. No genuine header/nav gap was found to fix —
  named here so this isn't silently skipped without having looked.

### Tests (TDD)

- `flutter_app/test/design_system/theme_test.dart` — new test asserts
  `MraTheme.light().colorScheme.primary == MraColors.brandPrimary` (and
  `onPrimary`), and the dark-theme equivalents against
  `brandPrimaryLight`/`brandDeepNavy` — would fail against the pre-fix
  seed-derived tone.
- `flutter_app/test/features/dashboard/dashboard_screen_test.dart` — new
  test asserts the sector field is found via
  `find.widgetWithType(MraSearchField, ...)` (would fail against the
  pre-fix hand-rolled `TextField`, which is a different runtime type),
  and that submitting text triggers a refetch.

**Validation run:**
```
cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# 156 files; ran clean after formatting the 2 new/changed test files

cd flutter_app && flutter test
# 242 tests passed, All tests passed! (was 240 before this follow-up — 2 new tests)
```

Visual verification: `flutter build web --release`, served locally,
Playwright screenshot confirmed the sign-in "Continue" button now
renders `#2563EB` (matching the logo) instead of the pre-fix muted tone.

### Conclusion

2 genuine gaps found and fixed: a brand-color fidelity bug traced to
Material's tonal-derivation algorithm (not previously checkable without
an actual rendered screenshot, which neither of this EPIC's prior
passes took), and a component-reuse gap this EPIC's own first pass had
partially touched but not fully caught. Header and navigation were
specifically checked via live screenshots across three destinations and
found consistent — not a silently-skipped claim. Re-confirming `DONE`.

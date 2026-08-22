# EPIC-M3.17 — Marksy Brand Identity, Logo & Product Theme Implementation

**Status:** IN_PROGRESS
**Execution Status:** FOUNDATION_COMPLETE — first pass done, dimension-by-dimension component/screen
audit still pending (see "Remaining work" below)
**Priority:** HIGH
**Product:** Marksy — Market Intelligence
**Source:** GitHub issue #300

## Objective

Implement the approved **Marksy** product identity across the Flutter app (icon, wordmark, color
theme), making the existing MRA application feel like one coherent branded product called Marksy,
without changing any API contract, business logic, or prediction/scoring behavior. Full scope as
originally specified is reproduced in issue #300; this doc records what was actually done.

## Reference asset

The approved reference board (a composite moodboard, not isolated source files) was located in the
user's Downloads folder and committed at `docs/branding/marksy/marksy-brand-reference.png`
(SHA-256 `c7250170668ce59bf4f8de864a0baa4695e372df5fa0b1732ddc5b5f221693ea`). See
`docs/branding/marksy/README.md` for the full asset inventory, extraction method, and documented
deviations (no true vector/SVG source exists to trace; some raster masters are upscaled from a
smaller native resolution than the spec's suggested minimums; the wordmark is implemented as real
text rather than more raster crops — rationale in that README).

## What was implemented this pass

1. **Brand tokens** (`design_system/tokens/mra_colors.dart`) — `brandPrimary` (the app's Material 3
   seed color) changed from the old placeholder navy (`#1B3A63`) to Marksy's Primary Blue
   (`#2563EB`), cascading through `ColorScheme.fromSeed` to `colorScheme.primary`/`secondary` app-wide
   (buttons, selected nav, links). Added `brandDeepNavy` (`#0A1E3A`), `brandTeal` (`#10B981`),
   `brandHighlight` (`#22D3EE`) as named tokens for direct use, all read from the reference board's
   own labeled swatches — no invented hex values. Existing semantic tokens (`positive`/`warning`/
   `error`/market-up/down) are untouched — brand color never overrides semantic meaning, per the
   epic's own rule.
2. **`MarksyLogo`/`MarksyIcon`/`MarksyWordmark`** (new: `design_system/components/marksy_logo.dart`,
   exported from the `design_system.dart` barrel) — the icon is a raster asset; the wordmark is real
   text (`Mark` in `onSurface`, `sy` in `brandTeal`) so it scales at any text-scale factor and adapts
   to theme brightness automatically, matching how the reference board itself shows the wordmark as
   styled text rather than a fixed logotype graphic.
3. **Wired into the app shell header** (`app_shell/app_shell_scaffold.dart`) — the app bar's literal
   `Text('MRA')` is now `MarksyLogo`, visible on every destination.
4. **Wired into auth** — `SplashScreen` (previously just a bare spinner) now shows the logo above it;
   `SignInScreen` shows the logo above the "Sign in" heading and its subtitle now reads
   "Marksy — Market Intelligence" (was "MRA — Market Research Agent").
5. **User-facing string sweep** — every literal `MRA` string that is real product UI (not an
   `MRA_*` backend API error code, which is a wire contract and out of scope per the epic's own
   "do not change backend/API contracts" rule) was updated to `Marksy`: `main.dart`'s `MaterialApp`
   title, the dev-only gallery screen's title, `general_settings_screen.dart`'s About section,
   `system_health_screen.dart`'s and `learning_screen.dart`'s descriptive copy, and
   `recommendation_detail_screen.dart`'s "Why Marksy selected this opportunity" section header.
6. **Web/PWA identity** — `web/index.html` (`<title>`, description, apple-mobile-web-app-title),
   `web/manifest.json` (`name`/`short_name`/`description`/`theme_color`/`background_color` now the
   Marksy deep-navy `#0A1E3A`, replacing the default Flutter blue `#0175C2`), and all four web
   icon/favicon files replaced with exports generated from the Marksy icon asset.
7. **Assets wired into the Flutter build** — `pubspec.yaml` now declares
   `assets/branding/marksy-icon-dark.png`, `marksy-icon-light.png`,
   `marksy-logo-horizontal-dark.png`.

## Remaining work (explicitly not done this pass — named, not silently skipped)

This epic's full scope (per issue #300) asks for a dimension-by-dimension audit of *every* screen
and component category: data grids/tables, charts, filters/dropdowns/dialogs, all loading/empty/
error/success states, pagination, breadcrumbs/tabs, tooltips, notifications, responsive/dark-theme/
accessibility/text-scale validation across every screen, plus additional logo variants (compact-nav,
light-background, monochrome — see the README for why those specific raster variants were not
produced this pass) and desktop (macOS/Windows/Linux) app icon conversion (ICNS/ICO — no conversion
tool available in this environment). None of that is done yet. The foundational layer above (tokens,
theme seed, reusable logo component, app shell + auth wiring, web identity) is what everything else
should build on, matching this repo's established pattern of an initial pass followed by a dedicated
follow-up audit pass (see EPIC-M3.16's own two-pass history for precedent).

## Tests

- `test/widget_test.dart` — updated to assert `find.text('Marksy')` instead of `find.text('MRA')`.
- `test/app_shell/app_shell_test.dart` — updated gallery-title assertion to `'Marksy Design System
  Gallery'`.
- `test/features/detail/recommendation_detail_screen_test.dart` — updated section-header assertion.
- `test/golden/goldens/{kpi_stat_row,recommendation_card_populated,sign_in_screen_compact}.png` —
  regenerated via `flutter test --update-goldens` since the new seed color and the sign-in screen's
  added logo both legitimately change rendered pixels.

**Validation run:**
```
cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# Formatted 152 files (0 changed)

cd flutter_app && flutter test
# 226 tests passed, All tests passed!
```

## Non-goals (unchanged from issue #300)

No trading/order execution changes, no prediction-model changes, no database/schema changes, no API
redesign, no business-logic rewrite.

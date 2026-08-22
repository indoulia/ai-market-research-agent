# Marksy Brand Reference

**Canonical visual reference:** [`marksy-brand-reference.png`](marksy-brand-reference.png)
(SHA-256 `c7250170668ce59bf4f8de864a0baa4695e372df5fa0b1732ddc5b5f221693ea`, 1536×1024, sourced from the
approved brand board supplied for EPIC-M3.17 / GitHub issue #300).

This board is a composite moodboard — multiple logo lockups, icon variants, and a color palette
stitched into one image — not a set of isolated source files (no vector/PSD/Figma source was
provided). Everything under `assets/` and `exports/` was cropped out of this single reference image.
Treat `marksy-brand-reference.png` itself as the source of truth for geometry and color; the files
below are derived, best-effort extractions for direct use in the app.

## Logo mark

The Marksy mark = a stylized **M** + a **candlestick** cluster + a **growth arrow**, in a blue → teal
gradient (see the "Logo Mark Breakdown" panel in the reference board).

- `assets/marksy-logo-horizontal-dark.png` — primary lockup (icon + "Marksy" wordmark + tagline) on
  its native dark-navy card background. Use as-is on dark/navy surfaces (app bar, splash, auth
  header). This is the cleanest extraction from the reference board — no visible neighboring bleed.
- `assets/marksy-app-icon-dark.png` / `assets/marksy-app-icon-light.png` — icon-only mark, each on its
  own rounded-square badge (dark-navy and white respectively), cropped from the reference board's app
  icon row. Use for compact nav, launcher, and favicon sources.
- `exports/web/favicon-32.png`, `exports/web/pwa-192.png`, `exports/web/pwa-512.png`,
  `exports/mobile/launcher-1024.png` — resized from `marksy-app-icon-dark.png` (native ~260×272) via
  Lanczos resampling to hit each platform's required pixel dimensions.

### Known deviations from the spec's asset list (documented, not silently skipped)

- **No SVG assets.** The reference board is a flattened raster composite with soft gradients/glow
  effects; there is no vector source to extract or trace faithfully, and hand-tracing a lookalike
  vector path would not match the approved artwork's real geometry. PNG is used everywhere instead.
  If/when the design team provides a true vector source (AI/Figma/SVG), swap it in at the same paths.
- **Raster masters below the spec's suggested minimums.** The icon's native resolution inside the
  composite board is ~260×272px — well under the "512×512 web source" / "1024×1024 mobile master"
  guidance. `exports/` upscales from that native asset via Lanczos to meet each platform's required
  pixel dimensions; this does not add real detail. Replace with a genuine high-resolution/vector master
  when one becomes available.
- **No separate light-background full lockup, compact-nav lockup, or monochrome fallback file.**
  The reference board's "Wordmark Variations" panel shows the `Marksy` wordmark as literal styled
  text (a bold sans-serif with the first four letters in one color and "sy" in a blue→green gradient),
  not a fixed logotype graphic — so the app renders the wordmark as real text (see below) instead of
  baking more raster wordmark images. This also makes light/dark theme adaptation exact instead of
  approximate, and avoids stacking more crops from a background that is a soft radial gradient
  everywhere on this board (no flat color anywhere to reliably chroma-key or auto-trim against, which
  is why extraction attempts at the wordmark-only and light-background rows were dropped rather than
  shipped in a visibly imperfect state).

## Wordmark

Render `Marksy` as real text, not an image: `Mark` in the primary text color, `sy` in a
`primaryBlue → teal` gradient (`ShaderMask` over a `TextSpan`), matching every wordmark variant shown
on the reference board. This scales correctly at any text-scale factor/density and adapts to
light/dark theme automatically, which a baked raster wordmark cannot do.

## Color palette (read directly off the reference board's own labeled swatches)

| Role | Hex | Reference label |
|---|---|---|
| Deep Navy | `#0A1E3A` | "Trust & Stability" |
| Primary Blue | `#2563EB` | "Intelligence" |
| Teal | `#10B981` | "Growth" |
| Blue/green highlight | `#22D3EE` | "Opportunity" |

These four are the brand tokens layered on top of the existing MRA semantic color system
(`positive`/`warning`/`error`/`info`/market-up/down) — brand color never overrides semantic meaning
per the epic's own rule.

## Prohibited modifications

Per the approved reference: never stretch, skew, rotate, recolor, crop into, or add drop
shadows/effects to the icon mark's geometry. The candlestick + arrow + M composition and its
blue→teal gradient direction are fixed. The wordmark's two-tone split (`Mark` / `sy`) is fixed;
don't recolor `Mark` away from the primary text color or `sy` away from the blue→green gradient.

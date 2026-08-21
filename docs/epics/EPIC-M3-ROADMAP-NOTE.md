# M3.x Roadmap — Combined UI+API Application Track

`docs/epics/EPIC-M3.1-*.md` through `EPIC-M3.15-*.md` are a combined
UI+API, vertical-slice application roadmap. These files previously
existed as `EPIC-M1.132-*.md` through `EPIC-M1.146-*.md`, colliding with
the existing split UI-only/API-only per-domain track that already owned
those same numbers (e.g. old `EPIC-M1.135-recommendations-api-and-query.md`
vs. the new, unrelated `EPIC-M1.135-recommendation-detail-prediction-timeline.md`).

**Resolution (2026-08-21, explicit user decision):** the original split
track (`M1.132`-`M1.148`) stays canonical — those numbers keep meaning
what their existing docs say. The newer combined roadmap was renumbered
into a fresh `M3.1`-`M3.15` namespace (mirroring the `M2.x` precedent) so
the two roadmaps no longer collide. No content was otherwise changed;
only the EPIC number and each file's `# EPIC-M3.N — ...` header line.

| New | Title | Was |
|---|---|---|
| M3.1 | MRA Application Platform Foundation | M1.132 |
| M3.2 | Market Overview & Home Dashboard | M1.133 |
| M3.3 | Opportunity Explorer | M1.134 |
| M3.4 | Recommendation Detail & Prediction Timeline | M1.135 |
| M3.5 | News & Corporate Events Intelligence | M1.136 |
| M3.6 | Discovery Intelligence | M1.137 |
| M3.7 | Performance & Trust Intelligence | M1.138 |
| M3.8 | Active Prediction Monitoring | M1.139 |
| M3.9 | Learning & Self-Improvement | M1.140 |
| M3.10 | User Feedback & Preferences | M1.141 |
| M3.11 | System & Provider Health | M1.142 |
| M3.12 | Authentication & User Session | M1.143 |
| M3.13 | Responsive, Accessibility & Performance | M1.144 |
| M3.14 | Application E2E Contract Validation | M1.145 |
| M3.15 | Longitudinal Tracking & Performance Analytics | M1.146 |

The old split-track `M1.132`-`M1.148` docs (API Contract & BFF
Foundation, Flutter Design System, Recommendations API and Query, etc.)
are unaffected by this change and continue to be executed under their
existing numbers.

**Also resolved (2026-08-22, explicit user decision): `M2.1`-`M2.3` vs `M3.1`.**
A third, still-earlier foundation track (`EPIC-M2.1-api-platform-contract.md`,
`EPIC-M2.2-flutter-design-system.md`, `EPIC-M2.3-app-shell-navigation-responsive-layout.md`)
defines the same API contract + Flutter design system + app shell concerns that
`EPIC-M3.1-mra-application-platform-foundation.md` recreates as part of the combined
roadmap above. None of the three M2.x docs were ever implemented. Per the user's
explicit decision, **M3 is authoritative going forward**: `M2.1`-`M2.3` are marked
`SUPERSEDED BY M3.1` in their own files (not deleted, preserved for history) and will
not be implemented. `M3.1` is implemented as the real foundation; `M3.2`-`M3.15` build
on it sequentially.

**Separately, a pre-existing, already-documented pattern** (unrelated to
this collision) has some earlier EPIC numbers with two files — an
unapproved draft plus a completed/approved duplicate (e.g. `M1.4`,
`M1.73`-`M1.89`). That is a different, older situation: always the same
topic at different approval stages, not two unrelated roadmaps competing
for one number. It is not addressed by this note; consult the approved
or `DONE` file for those numbers as already established practice.

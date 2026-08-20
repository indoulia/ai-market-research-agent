# EPIC-M1.10 — Positive Horizon Selection

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** ChatGPT  
**Priority:** P1

## Objective

Select and record the most appropriate positive recommendation horizon within the platform's 1–7 trading-day target, using deterministic evidence rather than a fixed default for every stock.

## Why now

The platform explicitly targets short horizons. A recommendation should state whether its positive opportunity is expected to mature in 1, 3, 5, or 7 trading days rather than treating all opportunities identically.

## Scope

1. Define supported horizons: 1, 3, 5, and 7 trading days.
2. Define deterministic horizon-selection rules based on available model/data evidence.
3. Record the selected horizon and the evidence/rule version used.
4. Handle insufficient data explicitly.
5. Add tests for each supported horizon and boundary conditions.

## Non-goals

- Long-term investment horizons.
- Automatic trading.
- Retrospective horizon changes after recommendation issuance.
- Learning/optimizing horizon rules from outcomes; that is a later EPIC.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Only 1/3/5/7 trading-day horizons can be issued.
- [ ] Horizon selection is deterministic and documented.
- [ ] Selected horizon is stored with the recommendation.
- [ ] Horizon selection cannot be silently changed after issuance.
- [ ] Insufficient evidence produces no invalid horizon.
- [ ] Tests cover all supported horizons and edge cases.

## Dependencies

- M1.8 — Positive Consensus Engine
- M1.4 — Persist Recommendation History

## Completion Report

<!-- Claude: populate this section only after implementation. Preserve review history; never erase prior review findings. -->

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->

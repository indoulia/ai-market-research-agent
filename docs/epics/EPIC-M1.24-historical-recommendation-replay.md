# EPIC-M1.24 — Historical Recommendation Replay

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** User  
**Priority:** P1

## Objective
Reconstruct historical recommendation decisions from point-in-time inputs so the system can validate rules, scores, confidence, discovery, and learning changes without future-data leakage.

## Scope
1. Replay historical recommendations using their original as-of timestamp.
2. Reconstruct only information that would have been available at that timestamp.
3. Recompute features, predictions, consensus, score, confidence, and horizon where required.
4. Compare replayed decisions with persisted original decisions.
5. Record replay configuration and software/model versions.
6. Detect data leakage or unavailable historical inputs explicitly.
7. Make replay deterministic and repeatable.

## Non-goals
- Changing historical production records.
- Production model promotion.
- Live trading.
- Using future outcomes as model inputs.

## Acceptance Criteria
- [ ] Historical replay is point-in-time safe.
- [ ] Future data cannot enter replay inputs.
- [ ] Replay is deterministic for identical inputs and versions.
- [ ] Original records remain immutable.
- [ ] Missing historical inputs produce explicit replay limitations.
- [ ] Replay differences are attributable to version/input changes.
- [ ] Tests cover leakage and reproducibility cases.

## Dependency Chain
### Previous / Required
- **M1.23 — Recommendation Confidence Analysis**
- **M1.12 — Market Universe & Daily Candidate Scan**
- **M1.13 — Positive Recommendation Generator**

### Next / Unlocks
- **M1.25 — Out-of-Sample Recommendation Validation**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Replay must never use information published after the historical decision timestamp. Any unavailable historical input must be surfaced rather than approximated silently.

## Completion Report
Update with implementation evidence, tests, PR/merge information, and final status before marking implemented.

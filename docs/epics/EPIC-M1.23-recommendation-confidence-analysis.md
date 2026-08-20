# EPIC-M1.23 — Recommendation Confidence Analysis

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Approved By:** —  
**Priority:** P1

## Objective
Measure whether reported prediction probabilities and confidence levels correspond to realized recommendation outcomes across horizons and evidence segments.

## Scope
1. Compare predicted probabilities with observed success rates.
2. Measure calibration by horizon and probability/confidence bucket.
3. Identify persistent over-confidence and under-confidence.
4. Report calibration error and sample sizes.
5. Segment confidence behavior by regime/sector/market-cap when sufficient evidence exists.
6. Produce deterministic, versioned analysis artifacts.
7. Preserve original issued confidence values.

## Non-goals
- Automatic confidence changes.
- Production model replacement.
- Rewriting historical recommendations.
- Trading decisions.

## Acceptance Criteria
- [ ] Calibration metrics are reproducible.
- [ ] Every confidence/probability metric includes sample count.
- [ ] Insufficient samples are explicit.
- [ ] Over-confidence and under-confidence can be identified objectively.
- [ ] Historical confidence remains immutable.
- [ ] Tests validate known calibration fixtures.

## Dependency Chain
### Previous / Required
- **M1.22 — Recommendation Score Analysis**
- **M1.16 — Recommendation Trust Report**

### Next / Unlocks
- **M1.24 — Historical Recommendation Replay**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
Confidence analysis must remain observational. Any calibration change must be versioned and separately validated before production use.

## Completion Report
Update with implementation evidence, tests, PR/merge information, and final status before marking implemented.

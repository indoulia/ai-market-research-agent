# EPIC-M1.11 — Recommendation Calibration Feedback Loop

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** ChatGPT  
**Priority:** P1

## Objective

Use completed recommendation outcomes to measure and improve probability calibration without changing the underlying prediction model in this EPIC.

## Why now

M1.5 and M1.6 create the objective outcome history needed to determine whether stated probabilities correspond to observed success rates. This is essential before claiming that a probability such as 70% has meaningful trust value.

## Scope

1. Group completed recommendations into probability buckets.
2. Compare predicted probability with observed success rate.
3. Calculate calibration error using a documented deterministic method.
4. Report calibration by horizon where sample size is sufficient.
5. Identify materially under- or over-confident probability ranges.
6. Preserve historical predictions; do not rewrite issued probabilities.
7. Add tests against known outcome fixtures.

## Non-goals

- Automatic model retraining.
- Changing historical recommendations.
- Changing the positive-consensus criteria.
- Creating recommendations.
- LLM-based calibration.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Calibration statistics are calculated only from objectively evaluated outcomes.
- [ ] Predicted probability and observed success rate are shown together.
- [ ] Sample size accompanies every calibration statistic.
- [ ] Calibration is available by supported horizon when sufficient data exists.
- [ ] Historical predictions remain immutable.
- [ ] Insufficient samples are explicitly marked rather than presented as reliable statistics.
- [ ] Tests verify calibration calculations against deterministic fixtures.

## Dependencies

- M1.5 — Evaluate Recommendation Outcomes
- M1.6 — Positive Recommendation Performance Report

## Completion Report

<!-- Claude: populate this section only after implementation. Preserve review history; never erase prior review findings. -->

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->

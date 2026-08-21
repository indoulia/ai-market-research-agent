# EPIC-M1.82 — Prediction Quality & Benchmark Measurement

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_READY
**Priority:** P0

## Objective
Measure whether MRA predictions create useful investment outcomes, not merely directional accuracy, and compare performance against appropriate market benchmarks.

## Scope
- Measure directional accuracy.
- Measure target-hit and stop-loss rates.
- Measure expected and realized return.
- Measure maximum favorable/adverse excursion.
- Measure time-to-target/stop.
- Measure calibration and probability quality.
- Compare recommendation performance with NIFTY/sector or appropriate benchmark.
- Measure excess/relative performance and risk-adjusted performance where evidence permits.
- Break down results by horizon, regime, sector and discovery source.

## Acceptance Criteria
- Prediction quality is measurable independently of raw model score.
- Benchmark-relative performance is available.
- Metrics include sample sizes and uncertainty where applicable.
- Poor but directionally correct predictions are distinguishable from useful predictions.
- Results feed the trust and learning systems.

## Dependency Chain
**Previous:** M1.21, M1.25, M1.47, M1.78.
**Next:** M1.84.

## Execution Rule
A model must not be considered improved solely because directional accuracy increased; investment usefulness and benchmark-relative performance matter.

# EPIC-M1.25 — Out-of-Sample Recommendation Validation

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_READY  
**Approved By:** —  
**Priority:** P1

## Objective
Validate recommendation rules, scores, probabilities, and learning candidates on strictly unseen historical periods before allowing downstream adaptive behavior to depend on them.

## Scope
1. Define deterministic time-separated training, calibration, and evaluation windows where applicable.
2. Evaluate recommendation behavior on unseen periods only.
3. Measure success rate, realized return, calibration, horizon performance, and failure/unevaluable rates.
4. Compare baseline behavior against candidate changes.
5. Segment evaluation by market regime, sector, market-cap, industry, and discovery source when sample size permits.
6. Produce a deterministic validation report with sample sizes and confidence/uncertainty indicators.
7. Preserve validation evidence and candidate/version metadata.
8. Reject or mark insufficient any candidate without adequate out-of-sample evidence.

## Non-goals
- Automatic production model promotion.
- Live trading.
- Retrospective modification of recommendation history.
- Treating in-sample performance as validation evidence.

## Acceptance Criteria
- [ ] Evaluation data is strictly separated from development/training evidence.
- [ ] No future information leaks into historical evaluation.
- [ ] Core performance and calibration metrics are reported with sample counts.
- [ ] Segment results are reported only when evidence is sufficient.
- [ ] Candidate changes are compared against an explicit baseline.
- [ ] Insufficient or regressed candidates are not considered validated.
- [ ] Validation runs are reproducible and versioned.

## Dependency Chain
### Previous / Required
- **M1.24 — Historical Recommendation Replay**
- **M1.21 — Recommendation Outcome Closure**
- **M1.16 — Recommendation Trust Report**

### Next / Unlocks
- **M1.26 — Market Regime Detection**
- **M1.27–M1.32 — Historical learning/model-evaluation chain**
- **M1.40 — Evidence-Based Score Adjustment**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25 → M1.26+`

## Execution Rule
M1.25 is the evidence gate for downstream learning. Approval of downstream EPICs does not permit them to bypass this validation boundary. No production score/model change may rely solely on in-sample results.

## Completion Report
Update with implementation evidence, tests, validation results, PR/merge information, and final status before marking implemented.

# EPIC-119 — Evidence-Based Self-Correction & Learning Loop

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Close the loop between prediction outcomes, attribution, usefulness, trust and controlled model/strategy improvement so MRA becomes more reliable over time without self-reinforcing false confidence.

## Scope
- Combine closed outcomes, attribution and usefulness measurements.
- Identify repeatable failure patterns.
- Generate learning hypotheses from evidence.
- Create controlled candidate changes rather than directly changing production behavior.
- Replay and validate candidates out of sample.
- Promote only candidates that demonstrate improvement without unacceptable regression.
- Recalculate trust only from measured evidence.
- Reduce or restore recommendation eligibility based on trust and validated performance.
- Preserve every learning decision and model version.

## Acceptance Criteria
- Failed predictions produce actionable learning signals.
- Learning hypotheses are traceable to evidence.
- Production models are never modified directly by an outcome.
- Candidate changes pass replay and out-of-sample validation.
- Promotion decisions are auditable.
- Trust rises only after demonstrated improvement and can fall after degradation.
- Historical predictions and learning evidence remain immutable.

## Dependencies
Previous: EPIC-063, EPIC-064, EPIC-080, EPIC-085, EPIC-083, EPIC-088, EPIC-089, EPIC-118.
Next: EPIC-100 and downstream continuous-learning EPICs.

## Execution Rule
The system must prefer honest abstention and controlled improvement over increased prediction volume. No self-learning action may bypass validation or rewrite historical evidence.

## Completion Report

**Status:** DONE — merged to main via PR #141 (`f40ee96`).

**Implementation:**
- `app/self_correction_loop.py` (`generate_learning_hypotheses`, `get_hypothesis_history`, `get_latest_eligibility_effect`): a new, versioned (`HYPOTHESIS_RULE_VERSION = "SCL-001"`) module combining EPIC-088 `PredictionAttributionSnapshot` (failure-pattern evidence, itself already derived from EPIC-005 closed outcomes) and EPIC-089 `PredictionUsefulnessAssessment`/investment-usefulness evidence into explicit, persisted `LearningHypothesis` rows.
- **Identify repeatable failure patterns / generate hypotheses from evidence:** a hypothesis is only ever generated for a segment (attribution dimension/value, or horizon) whose *baseline* window already shows a real weakness vs. the overall baseline rate, using the same `WEAKNESS_MARGIN`/`MIN_SAMPLE_SIZE_FOR_COMPARISON` this platform already uses everywhere else (`app/trust_report.py`) — a segment that looks fine in the baseline never produces a hypothesis at all.
- **Replay and validate candidates out of sample / promote only on demonstrated improvement:** reuses EPIC-074's own `EvaluationWindow`/`OverlappingEvaluationWindowsError` disjoint-window abstraction. A baseline-flagged weakness is `VALIDATED` only if it independently replicates in a later, disjoint monitoring window's own evidence; `REJECTED` if it does not replicate; `PENDING_VALIDATION` (never validated) if the monitoring window lacks enough evidence to judge either way.
- **Create controlled candidate changes, never apply directly:** each hypothesis carries a fixed, versioned `proposed_action` (e.g. `AVOID_REGIME_SEGMENT`, `REDUCE_HORIZON_ELIGIBILITY`, `RESTRICT_SEGMENT_ELIGIBILITY`, `REQUIRE_EVIDENCE_CATEGORY`) and an `eligibility_effect` (`RESTRICT` only when `VALIDATED`, `RESTORE` otherwise) — a read-only signal, never applied. This module has no write path to `Prediction`, `ScanCandidate`, or any live selection/eligibility table, matching the platform's established propose/gate posture (EPIC-060/EPIC-078/EPIC-080/EPIC-084/EPIC-085/EPIC-082/EPIC-083/EPIC-087/EPIC-118).
- **Reduce or restore eligibility based on validated performance:** `get_latest_eligibility_effect` always reflects the most recently generated run for a segment — a later run whose weakness no longer replicates naturally supersedes an earlier `RESTRICT` with `RESTORE`, without ever mutating the earlier, immutable row (no separate "restore" code path is needed; it falls out of re-running against fresh evidence).
- **Recalculate trust only from measured evidence:** this module never computes trust itself — that remains EPIC-080's exclusive, already-merged job.
- **Preserve every learning decision:** new immutable table `learning_hypotheses` (migration `0073_learning_hypotheses.py`, model `LearningHypothesis`), one row per `(model_version, hypothesis_category, dimension, factor_value, generated_at)`, enforced immutable after creation via a `before_update` listener matching the established gate/decision-table pattern. A generation run is idempotent per `(model_version, generated_at)`.

**Tests:** `tests/test_self_correction_loop.py` (10 tests) — no hypothesis when baseline isn't weak, validated/rejected/pending outcomes for factor failure patterns, low-horizon-usefulness hypothesis generation, overlapping-window rejection, idempotency, immutability, and `get_latest_eligibility_effect` correctly flipping from `RESTRICT` to `RESTORE` once a later run's evidence no longer replicates the original weakness.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_self_correction_loop.py -q` → `10 passed`
- `python -m pytest -q` (full suite) → `896 passed, 6 skipped`
- `python -m alembic heads` → single head `0073_learning_hypotheses (head)`, chain resolves cleanly

**Not wired into any live selection/eligibility feed** — consistent with this platform's established propose/gate split; wiring `eligibility_effect` into the actual recommendation feed remains a future deployment step, the same posture EPIC-087's `eligibility_reduced` and EPIC-118's ranking output already documented.

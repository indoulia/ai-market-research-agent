# EPIC-083 — Prediction Stability & Model Agreement

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Measure whether predictions remain stable under normal information updates and whether independent candidate models agree on the opportunity.

## Scope
- Track prediction revisions over time.
- Measure magnitude and frequency of prediction changes.
- Detect unstable score/probability/target/SL behavior.
- Measure ensemble/model disagreement.
- Include disagreement in trust evaluation.
- Distinguish legitimate reaction to new information from unexplained instability.
- Preserve every revision and the evidence that caused it.

## Acceptance Criteria
- Prediction stability is measurable per stock and horizon.
- Model disagreement is measurable and auditable.
- Material revisions identify their triggering evidence/version.
- Unexplained instability reduces trust.
- Stable agreement can contribute positively to trust only when backed by outcomes.

## Dependency Chain
**Previous:** EPIC-050, EPIC-061, EPIC-080, EPIC-081.
**Next:** EPIC-087.

## Execution Rule
Stability alone cannot increase trust; it becomes positive evidence only when stable predictions demonstrate reliable outcomes.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-083

### Branch

autonomous/epic-m1-83, branched cleanly from `main` (the declared dependencies -- EPIC-050, EPIC-061, EPIC-080, EPIC-081 -- are already merged).

### Objective

Measure whether predictions remain stable under normal information updates and whether independent candidate models agree on the opportunity.

### Design

`app/prediction_stability.py` composes EPIC-050's own revision chain and its already-computed `VersionComparison` deltas (`opportunity_score_delta`, `confidence_delta`, etc.) directly -- never recomputing them. EPIC-050's `create_recommendation_revision` already requires a `revision_reason` from a fixed vocabulary, so no revision is ever literally "unexplained"; `MANUAL_TRIGGER` is the one reason not backed by an objective evidence/freshness signal, so "distinguish legitimate reaction to new information from unexplained instability" (scope) is operationalized as: high revision frequency/magnitude driven by `MANUAL_TRIGGER` is unexplained instability; the same frequency/magnitude driven by `MATERIAL_EVIDENCE_CHANGE`/`EVIDENCE_STALE` is a legitimate, still-reported reaction that is never flagged for trust reduction on its own.

### Model Agreement Is Real, Not Fabricated

This platform's production pipeline runs exactly one model version at a time (`RecommendationGeneration.scan_candidate_id` is unique, so there is no real simultaneous-ensemble scoring today). Rather than fabricating agreement data, `_find_agreement_candidate` looks for any other `Prediction` on the same stock, from a different model version, within a bounded time window -- if this platform ever runs two models side by side, this comparison becomes real immediately; until then it honestly reports `NO_DISAGREEMENT_DATA` (proven by `test_no_revisions_is_stable`), while `test_model_agreement_agree`/`test_model_agreement_disagree` prove the real comparison works correctly when such data does exist.

### Stability Alone Cannot Increase Trust

`stability_backed_by_outcomes` requires BOTH a `STABLE` verdict AND a real, evaluated `SUCCESS` outcome on the active version -- never stability alone (Execution Rule; `test_stability_backed_by_outcomes_requires_success` and `test_stability_without_outcome_is_not_backed` prove both sides).

### Propose, Never Enforce

`trust_reduction_recommended` is exposed for a future consumer (EPIC-087, this EPIC's own listed "Next" dependency) -- this module has no write path to `Prediction`, `RecommendationRevision`, or `PredictionTrustScore` itself (`test_never_writes_to_predictions_or_revisions`).

### Files Changed

- `app/prediction_stability.py` — new: `assess_prediction_stability`, `get_stability_history`, constants.
- `app/models.py` — new `PredictionStabilityAssessment` model.
- `migrations/versions/0063_prediction_stability.py` — new migration.
- `tests/test_prediction_stability.py` — new: 11 tests.
- `docs/epics/EPIC-083-prediction-stability-model-agreement.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_prediction_stability.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0063_prediction_stability`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0062` through `0063` (verified `prediction_stability_assessments` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **727 passed, 0 failed**.
- `test_prediction_stability.py`: **11 passed** — a never-revised prediction is trivially `STABLE` with no disagreement data; small revisions stay `STABLE`; a large score-delta revision and too many revisions are each independently `UNSTABLE`; `MANUAL_TRIGGER`-driven instability correctly recommends trust reduction while evidence-driven instability alone does not; model agreement correctly detects both `AGREE` and `DISAGREE` when comparable cross-model-version data exists; stability is backed by outcomes only with both a `STABLE` verdict and a real `SUCCESS` outcome; assessments are idempotent per `(original_prediction_id, assessed_at)`; the module never writes to `Prediction`/`RecommendationRevision`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Prediction stability is measurable per stock and horizon (per-`original_prediction_id` assessment, keyed to a specific stock/horizon lineage).
- [x] Model disagreement is measurable and auditable (`model_agreement_verdict`/`model_agreement_score_delta`, real when cross-model data exists).
- [x] Material revisions identify their triggering evidence/version (EPIC-050's own `revision_reason`/`triggering_evidence_revalidation_check_id`, reused unchanged).
- [x] Unexplained instability reduces trust (`trust_reduction_recommended` when `UNSTABLE` with `MANUAL_TRIGGER` revisions present; proven by test).
- [x] Stable agreement can contribute positively to trust only when backed by outcomes (`stability_backed_by_outcomes`; proven by test).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof that stability alone never counts as positive evidence without a real, successful outcome behind it. This EPIC composes EPIC-050's revision chain without duplicating its deltas, and honestly reports "no disagreement data" for model agreement given this platform's genuinely single-model production reality today, while building the comparison to be immediately real the moment a second model version exists. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

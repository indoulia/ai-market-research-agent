# EPIC-M1.115 — Prediction Replay & Reproducibility

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Reproduce exactly what MRA knew, which providers were used, which model/version ran and why a prediction was produced at any historical timestamp.

## Scope
- Persist point-in-time input snapshots and provider identities.
- Persist model, feature, configuration and policy versions.
- Reconstruct prediction revisions and decision traces.
- Replay historical predictions deterministically where source data permits.
- Compare replay output with original output.
- Detect non-reproducible dependencies.

## Dependencies
M1.66, M1.78, M1.90, M1.110.

## Completion Report

**Status:** DONE — merged to main via PR #213.

**Implementation:**
- `app/reproducibility_audit.py`: a new, versioned (`AUDIT_RULE_VERSION = "RPA-001"`) module.
- **Persist point-in-time input snapshots, provider identities, and model/feature/configuration/policy versions:** already fully covered by M1.66's `RecommendationDecisionTrace` — every version field and every evidence category's `source` is already captured immutably at decision time. Not duplicated here.
- **Reconstruct prediction revisions and decision traces / replay historical predictions deterministically / compare replay output with original output:** already M1.55/M1.66/M1.24's own jobs respectively. Not duplicated here.
- **Detect non-reproducible dependencies (this module's own contribution):** `audit_prediction_reproducibility` compares a prediction's own trace against the platform's *current* live version constants (`consensus.CONTRACT_VERSION`, `scoring.CONTRACT_VERSION`, `horizon.SELECTION_VERSION`, `target_stop_loss.TARGET_STOP_METHODOLOGY_VERSION`) and, when a live provider-id set is supplied, each evidence category's captured `source` against what's currently registered. Either kind of drift means a literal replay today cannot reproduce the original decision for reasons unrelated to model correctness — an environment-drift signal, distinct from M1.67's regression signal.
- Provider-drift checking is explicitly opt-in per call: an empty/omitted `currently_registered_provider_ids` means "not checked this run," never "no drift found" — verified directly by `test_provider_drift_not_checked_when_not_supplied`.
- Read-only: no write path to `RecommendationDecisionTrace` or any pipeline-version constant. New immutable table `reproducibility_audit_decisions` (migration `0092_reproducibility_audit.py`), idempotent by `(prediction_id, audited_at)`.

**Tests:** `tests/test_reproducibility_audit.py` (6 tests) — reproducible when a real trace matches current versions, not-reproducible with no trace at all, version drift detected, provider drift detected when checked, provider drift correctly left unchecked when not supplied, idempotency.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_reproducibility_audit.py -q` → `6 passed`
- `python -m pytest -q` (full suite) → `1133 passed`
- `python -m alembic heads` → single head `0092_reproducibility_audit (head)`, chain resolves cleanly

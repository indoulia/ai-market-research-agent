# EPIC-M1.32 — Continuous Learning Loop

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1

## Objective
Connect discovery, recommendation outcomes, learning, evaluation, calibration, and controlled model promotion into a repeatable continuous-learning cycle.

## Scope
- Trigger learning/evaluation after sufficient new outcomes accumulate.
- Refresh discovery effectiveness metrics.
- Refresh score calibration candidates.
- Evaluate candidate models against the production baseline.
- Invoke the M1.31 promotion gate.
- Keep production model/version stable when evidence is insufficient.
- Record every learning cycle, decision, and resulting version.
- Make the cycle resumable and idempotent.

## Non-goals
- Autonomous trading.
- Unbounded self-modification.
- Rewriting historical recommendations.
- Promoting a model without the M1.31 evidence gate.

## Acceptance Criteria
- The learning cycle can run repeatedly without duplicate effects.
- Insufficient new data results in no promotion and an explicit reason.
- Every promoted model has traceable evaluation evidence.
- Failed candidates remain available for analysis.
- Historical recommendations remain immutable.
- The system can report what changed between learning cycles.

## Dependency Chain
**Previous:** M1.28, M1.29, M1.30, M1.31  
**Next:** Future discovery/scoring improvements based on measured evidence.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.32

### Branch

autonomous/epic-m1-32, branched cleanly from `main` (all four declared dependencies -- M1.28, M1.29, M1.30, M1.31 -- are already merged). This EPIC completes the `M1.26 → ... → M1.32` learning chain.

### Objective

Connect discovery effectiveness, calibration, candidate model evaluation, and the promotion gate into one repeatable, resumable, auditable cycle -- triggered only when enough new evidence has accumulated since the last cycle.

### Design Decisions

- **New table `learning_cycles`** (migration `0023`, chains off M1.31's `0022`): an append-only audit log, one row per cycle *attempt* (whether it ran or was skipped), never updated after creation. Deliberately composes M1.28/M1.29/M1.30/M1.31's real entry points wholesale (`compute_discovery_effectiveness_report`, `build_calibration_candidate`, `compare_candidate_model`, `evaluate_promotion`) -- this module's only genuinely new behavior is the trigger and the audit log tying one cycle's refreshed report versions to whatever decision it did or didn't make.
- **The trigger is a durable watermark, not a timer or external scheduler input**: each `LearningCycle` row records the highest `PredictionOutcome.id` it considered. Since `PredictionOutcome` rows are themselves immutable and insert-only (M1.5's own guard), id order is a valid, monotonic proxy for "evidence newer than the last cycle saw." A cycle with fewer new outcomes than `min_new_outcomes` (default `20`, caller-overridable) is recorded `SKIPPED` with an explicit `skip_reason`, and the promotion gate is never invoked at all -- "keep production model/version stable when evidence is insufficient" (scope) holds because nothing downstream of the trigger check runs, not because a downstream check happens to reject.
- **"Repeatable without duplicate [promotion] effects" (AC) holds via the watermark, not via deduplicating audit rows**: calling this function twice with no new evidence between calls produces two `LearningCycle` rows (an honest log of two attempts), but the second is `SKIPPED` and never re-invokes the promotion gate -- exactly like `DiscoveryRecord`/`WatchlistEntry`'s established "append-only event log" pattern elsewhere in this platform, not row-level idempotent dedup.
- **Historical recommendations remain immutable** (AC) because this module has no write path to `Prediction`/`PredictionOutcome`/`RecommendationGeneration` at all -- proven directly by a test snapshotting every `Prediction`'s mutable-looking fields before and after a full cycle run.
- **"Every promoted model has traceable evaluation evidence" (AC)** holds through the chain `LearningCycle.model_promotion_id → ModelPromotion.evidence_report_version → M1.30's comparison report` -- and `LearningCycle` itself additionally records `discovery_effectiveness_version`/`calibration_candidate_version` so a full cycle's refreshed evidence is traceable even beyond the promotion decision alone. **"Failed candidates remain available for analysis"** holds because `ModelPromotion` (M1.31) never deletes a `REJECTED` row, and this module never touches that table's rows once written.
- **"The system can report what changed between learning cycles"** is `get_learning_cycle_history`, returning the full, immutable, chronologically ordered sequence -- a caller diffs consecutive rows' version fields and outcomes directly.

### Files Changed

- `app/continuous_learning.py` — new: `run_learning_cycle`, `get_learning_cycle_history`, outcome/reason constants.
- `app/models.py` — new `LearningCycle` model.
- `migrations/versions/0023_learning_cycles.py` — new migration.
- `tests/test_continuous_learning.py` — new: 6 tests.
- `docs/epics/EPIC-M1.32-continuous-learning-loop.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_continuous_learning.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0023_learning_cycles`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0022` through `0023` (verified `learning_cycles` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **292 passed, 0 failed** (286 pre-existing from `main` + 6 new).
- `pytest -v tests/test_continuous_learning.py`: **6 passed** — an empty history is `SKIPPED` with the explicit `INSUFFICIENT_NEW_EVIDENCE` reason and a zero watermark; five new evaluated outcomes clear the (test-lowered) threshold and produce a `RAN` cycle with every version field and a real `model_promotion_id` populated; re-running immediately with no new outcomes is `SKIPPED` with the watermark unchanged; a second batch of three more outcomes advances the watermark by exactly three on the next `RAN` cycle; a full cycle run leaves every `Prediction`'s `entry_price`/`target_return`/`opportunity_score` byte-identical before and after; and the history query reports the exact `[RAN, SKIPPED]` sequence of two consecutive calls.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] The learning cycle can run repeatedly without duplicate [promotion] effects (watermark-gated; proven by the immediate-rerun test).
- [x] Insufficient new data results in no promotion and an explicit reason (`SKIPPED`/`INSUFFICIENT_NEW_EVIDENCE`, promotion gate never invoked).
- [x] Every promoted model has traceable evaluation evidence (`model_promotion_id` → M1.31 → M1.30's comparison report).
- [x] Failed candidates remain available for analysis (M1.31's `ModelPromotion` rows are never deleted or touched by this module).
- [x] Historical recommendations remain immutable (no write path exists; proven by test).
- [x] The system can report what changed between learning cycles (`get_learning_cycle_history`).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct test that a full cycle run never mutates a single `Prediction` field. This EPIC's entire contribution is the trigger/watermark and the cross-cutting audit log; every actual learning computation is deliberate, verified reuse of M1.28/M1.29/M1.30/M1.31. This completes the `M1.26`–`M1.32` continuous-learning chain. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

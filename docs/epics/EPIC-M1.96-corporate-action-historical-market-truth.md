# EPIC-M1.96 — Corporate Action & Historical Market Truth

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Ensure historical prices, securities, identities and outcomes remain economically correct across corporate actions and security lifecycle changes.

## Scope
- Handle splits, bonuses, dividends, rights and relevant corporate actions.
- Handle symbol/identifier changes, mergers, demergers and delistings where applicable.
- Preserve raw and adjusted representations with provenance.
- Ensure historical predictions and returns use the correct economic basis.
- Prevent survivorship bias caused by excluding securities that later disappeared.
- Version corporate-action data and correction history.
- Add reconciliation and historical-return tests.

## Acceptance Criteria
- Historical returns remain correct across corporate actions.
- Security identity changes are traceable.
- Delisted/changed securities are not silently removed from historical datasets.
- Prediction outcomes remain reproducible after data corrections.

## Dependencies
Previous: M1.72, M1.95.
Next: M1.97.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.96

### Branch

autonomous/epic-m1-96, branched cleanly from `main` (both declared dependencies -- M1.72, M1.95 -- are already merged).

### Objective

Ensure historical prices, securities, identities and outcomes remain economically correct across corporate actions and security lifecycle changes.

### What Was Actually Missing

Before writing code I confirmed there was zero corporate-action infrastructure anywhere in this codebase: no model, no split/dividend adjustment, no delisting workflow (`Stock.is_active` was never actually set to `False` anywhere in production code), and no symbol-change tracking. `Stock.is_active` already existed and, verified by grep, is only ever filtered on by three genuinely live-only concerns (`app.market_data.ingest`'s refresh-candidate query, `app.scan`'s daily-scan universe, and the personal-watchlist modules) -- no historical report in this platform filters by it, and nothing ever deletes a `Stock` row. So "delisted/changed securities are not silently removed from historical datasets" (AC) was already structurally true; what was missing was a *traced, versioned way to actually record a delisting* at all.

### New: `CorporateAction` (`app/corporate_actions.py`)

An append-only, immutable table recording `SPLIT`/`BONUS`/`RIGHTS`/`DIVIDEND`/`SYMBOL_CHANGE`/`MERGER`/`DEMERGER`/`DELISTING` events, each carrying `action_version` (`CORPORATE_ACTION_VERSION = "CPA-001"`) and validated per type (a ratio-bearing action requires a positive `ratio`; a dividend requires a positive `cash_amount`; a symbol change requires `new_symbol`). Two action types apply one real, traced side effect instead of leaving `Stock` to be mutated ad hoc elsewhere: `SYMBOL_CHANGE` renames `stock.symbol` while the immutable action row permanently preserves the old/new pair (AC: "security identity changes are traceable"); `DELISTING` flips `stock.is_active` through this same auditable path.

### Raw Prices Are Never Touched; Adjustment Is a Pure, Derived Read

`compute_price_adjustment_factor(session, stock_id, reference_date, price_date)` computes the cumulative product of every `SPLIT`/`BONUS`/`RIGHTS` action's `ratio` with `reference_date < effective_date <= price_date` -- the factor that brings a later raw price back onto an earlier reference date's economic basis. It never mutates a `MarketPrice` row (scope: "preserve raw and adjusted representations with provenance") and returns exactly `Decimal("1")` -- a true no-op -- whenever a stock has no qualifying corporate action, which `test_evaluate_recommendation_is_unaffected_when_no_corporate_action_recorded` and the full pre-existing `test_outcome_evaluation.py` suite (unmodified, all still passing) prove has zero regression risk.

**Cash dividends are recorded for provenance but deliberately not applied as a price adjustment.** Doing so correctly requires estimating the pre-ex-date closing price -- a real, separate estimation problem this EPIC does not fabricate an answer to (the same honesty discipline M1.82/M1.86 already established for benchmark data this platform doesn't have). **Mergers/demergers are recordable but not auto-stitched** across two different `Stock` rows -- that requires a predecessor/successor security mapping this data model does not have, and inventing one risks silently misrepresenting history rather than honestly leaving it unhandled. Both limitations are named explicitly in the module docstring, not silently omitted.

### Wired Into `app/outcomes.py` With a Provable Zero-Regression Guarantee

"Historical returns remain correct across corporate actions" (AC) required actually composing this into `evaluate_recommendation`, not just building an unused utility. Each window day's high/low/close is now adjusted onto the prediction's own `as_of_timestamp` basis (via a new `_adjusted_window`/`_AdjustedBar` helper) before any target/stop comparison or return calculation; the pre-existing `_has_valid_ohlc` data-quality check still runs against the *raw* rows, since an adjustment must never mask genuinely bad source data. `test_evaluate_recommendation_uses_split_adjusted_basis_to_detect_a_real_target_hit` and its companion `test_evaluate_recommendation_without_adjustment_would_have_missed_the_target_hit` prove this is a real correctness fix (a 2:1 split's post-split raw prices, unadjusted, would be misread as a stop-loss hit; adjusted, they correctly resolve to the target actually being hit) -- and the full 853-test suite passing unchanged proves it introduces no regression for the overwhelming majority of predictions that never encounter a corporate action.

### Files Changed

- `app/models.py` — new `CorporateAction` model.
- `app/corporate_actions.py` — new: `record_corporate_action`, `get_corporate_actions`, `compute_price_adjustment_factor`, `adjust_price`, action-type constants, immutability guard.
- `app/outcomes.py` — `evaluate_recommendation` now adjusts each window day onto the prediction's entry-date basis via a new `_adjusted_window`/`_AdjustedBar` helper before computing `highest_price`/`lowest_price`/`closing_price`/target-stop exit/`actual_return`.
- `migrations/versions/0069_corporate_actions.py` — new table, additive; `downgrade()` drops it cleanly.
- `tests/test_corporate_actions.py` — new: 17 tests.
- `docs/epics/EPIC-M1.96-corporate-action-historical-market-truth.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_corporate_actions.py tests/test_outcome_evaluation.py tests/test_prediction_label_contract.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0069_corporate_actions`)
- Real PostgreSQL (`market_agent` DB): `alembic upgrade head` (created the table), verified via `sqlalchemy.inspect` that all columns/types/index match the model, `alembic downgrade -1` (verified the table was dropped), `alembic upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **853 passed, 0 failed** (836 pre-existing + 17 new).
- `test_corporate_actions.py`: **17 passed** — per-type validation (split/bonus/rights require a ratio, dividend requires a cash amount, symbol change requires a new symbol, unknown types rejected); a recorded action carries its version and is immutable; symbol change renames the stock and preserves old/new history; delisting flips `is_active` through the traced path; a delisted stock's prediction remains fully queryable in historical data; the adjustment factor is 1 with no actions, 1 when `price_date` isn't after `reference_date`, correctly applies a single split, correctly excludes an action exactly on the reference date, correctly multiplies across two sequential actions; a dividend is recorded but never adjusts price; `evaluate_recommendation` is provably unaffected with no corporate action recorded; a real split-adjusted target-hit is correctly detected, and the same unadjusted data is shown to have been wrongly read as a stop-loss hit without the fix.
- `test_outcome_evaluation.py` (pre-existing, unmodified): all 14 tests still pass, proving zero regression.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Real-Postgres migration round-trip: table created with matching schema, dropped on downgrade, cleanly re-applied on upgrade.

### Acceptance Criteria

- [x] Historical returns remain correct across corporate actions (`evaluate_recommendation`'s new split/bonus/rights-adjusted basis, proven by the before/after split test pair).
- [x] Security identity changes are traceable (`CorporateAction.old_symbol`/`new_symbol`, immutable, permanent).
- [x] Delisted/changed securities are not silently removed from historical datasets (structural, verified by grep across every `is_active` filter site; proven again by `test_delisted_stock_predictions_remain_in_historical_query`).
- [x] Prediction outcomes remain reproducible after data corrections (a `CorporateAction` is itself immutable once recorded, and `PredictionOutcome` remains immutable per M1.5/M1.95 -- a correction is always a new, later-recorded action, never a rewrite of an already-computed outcome).

### Claude Assessment

I believe this implementation satisfies all four acceptance criteria with real, verified evidence, including a genuine correctness fix (not just new unused infrastructure) proven with a concrete before/after test pair, and a proven zero-regression guarantee for the vast majority of predictions unaffected by any corporate action. Dividend price-continuity and merger/demerger price-series stitching are explicitly named as out-of-scope limitations rather than fabricated. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

# EPIC-M1.17 — ChatGPT Candidate Discovery

**Status:** APPROVED  
**Execution Status:** VALIDATING  
**Approved By:** User  
**Priority:** P2

## Objective

Allow ChatGPT-assisted discovery of stocks to investigate while keeping final positive recommendation qualification entirely inside the deterministic quantitative engine.

## Scope

1. Define an input contract for externally discovered candidate stocks.
2. Record discovery source, timestamp, and rationale without treating rationale as quantitative evidence.
3. Route discovered candidates through the same market-data, prediction, positive-consensus, scoring, and horizon evaluation as internally discovered candidates.
4. Produce a clear result: qualifying positive candidate or `NOT MATCHING POSITIVE CONSENSUS`.
5. Persist discovery provenance separately from recommendation evidence.
6. Add tests proving discovery input cannot bypass quantitative qualification.

## Non-goals

- Allowing ChatGPT to directly create recommendations.
- LLM-generated probability or success percentages.
- Trading automation.
- Replacing the quantitative engine.
- UI/dashboard work.

## Acceptance Criteria

- [ ] External discovery candidates use the same quantitative evaluation path as internal candidates.
- [ ] Discovery rationale is clearly separated from quantitative evidence.
- [ ] ChatGPT cannot bypass positive-consensus qualification.
- [ ] Non-qualifying candidates are explicitly recorded as `NOT MATCHING POSITIVE CONSENSUS` where applicable.
- [ ] Discovery provenance is traceable.
- [ ] Tests demonstrate bypass prevention.

## Dependency Chain

### Previous / Required
- **M1.8 — Positive Consensus Engine** — defines the positive qualification gate.
- **M1.13 — Positive Recommendation Generator** — provides the same quantitative recommendation path used by internally discovered candidates.

### Next / Unlocks
- No downstream EPIC is currently committed. Future discovery enhancements must be separately defined and approved.

### Chain Position

`M1.8 → M1.13 → M1.17`

M1.17 is a side branch from the core recommendation path. It does **not** require M1.14, M1.15, or M1.16 to execute.

### Execution Rule

Do not execute M1.17 until M1.8 and M1.13 are implemented, reviewed, and merged. ChatGPT discovery must never bypass quantitative qualification.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.17

### Branch

autonomous/epic-m1-17, branched cleanly from `main` (both declared dependencies, M1.8 and M1.13, are already merged; per the EPIC's own Chain Position note, M1.14/M1.15/M1.16 are not required).

### Objective

Let an externally (e.g. ChatGPT-assisted) discovered candidate stock be evaluated through exactly the same market-data, prediction, positive-consensus, scoring, and horizon pipeline as an internally (M1.12 scan) discovered candidate, while its discovery rationale is persisted purely as provenance and can never influence or bypass that evaluation.

### Design Decisions

- **New table `discovery_records`** (migration `0016`, chains off M1.15's `0015`; independent of M1.14): one row per `(scan_id, stock_id, source)`, recording `rationale` (free text), `discovered_at`, and `recommendation_generation_id` (nullable, populated once routed).
- **`record_discovery(session, *, scan_id, stock_id, rationale, discovered_at, source=SOURCE_CHATGPT)`** (`app/discovery.py`) persists provenance only — no consensus/scoring/horizon code path reads this function's inputs at all. Idempotent by the table's unique constraint: re-recording the same `(scan_id, stock_id, source)` returns the original row (and its original rationale) unchanged, never overwriting it with a newer one (scope item 5).
- **`route_discovery_through_pipeline(session, discovery, *, as_of_timestamp, entry_price, target_return, stop_return)`** looks up the `ScanCandidate` row that the M1.12 scan already computed for `(discovery.scan_id, discovery.stock_id)`, then calls M1.13's real `generate_recommendation_for_candidate` on it — the *identical* function and code path internally discovered candidates use, with no ChatGPT-specific branch anywhere in M1.8/M1.9/M1.10/M1.13. This is what makes bypass impossible by construction rather than by a check: the rationale string is never passed into this call and has no argument position it could occupy (scope items 2, 3, 6).
  - If the stock has no `ScanCandidate` in that scan at all, raises `DiscoveryCandidateNotInScanError` explicitly rather than fabricating a candidate from the rationale alone.
  - If the scan already excluded the stock (`eligible=False`, e.g. `missing_market_data`), `generate_recommendation_for_candidate`'s own `CandidateNotEligibleError` propagates unchanged — deliberately not special-cased for external discovery, since an internally discovered candidate in the same state fails identically.
  - Idempotent: a `discovery` already linked to a generation returns that generation directly rather than calling the generator (or M1.13's own idempotency check) again.
- **Non-qualifying-outcome vocabulary:** the EPIC's AC references `NOT MATCHING POSITIVE CONSENSUS`, which is `app/watchlist.py`'s (M1.7) label for the same underlying consensus decision. That path evaluates consensus alone and takes score/horizon as caller-supplied kwargs, but this EPIC's scope explicitly requires the fuller scoring (M1.9) + horizon-selection (M1.10) pipeline, which only exists via M1.13's `generate_recommendation_for_candidate` — whose own vocabulary is `OUTCOME_NOT_QUALIFIED = "NOT_QUALIFIED"`. This module therefore treats `OUTCOME_NOT_QUALIFIED` as the applicable equivalent for a routed-through discovery, documented here for reviewer scrutiny per this repo's established convention for ambiguous-phrasing decisions (see M1.6's probability/confidence bucket note).
- No OpenAI/ChatGPT API call is made anywhere in this implementation. `source` is a plain string tag (`SOURCE_CHATGPT = "CHATGPT"`) identifying who supplied the candidate symbol + rationale as external input to `record_discovery`; the EPIC's own non-goals rule out any LLM-generated probability/evidence, so there is nothing here that should call an LLM.

### Files Changed

- `app/discovery.py` — new: `record_discovery`, `route_discovery_through_pipeline`, `DiscoveryCandidateNotInScanError`, `SOURCE_CHATGPT`.
- `app/models.py` — new `DiscoveryRecord` model.
- `migrations/versions/0016_discovery_records.py` — new migration.
- `tests/test_discovery.py` — new: 8 tests.
- `docs/epics/EPIC-M1.17-chatgpt-candidate-discovery.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_discovery.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0016_discovery_records`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0015` through `0016` (verified `discovery_records` created), `downgrade -1` (verified dropped back to `0015`), `upgrade head` again (clean re-apply). `current` confirmed `0016_discovery_records` throughout.

### Test Results

- `pytest -q`: **175 passed, 0 failed** (167 pre-existing from `main` + 8 new).
- `pytest -v tests/test_discovery.py`: **8 passed** — provenance fields (source/rationale/discovered_at) persist correctly with no generation linked yet; re-recording the same `(scan, stock, source)` is idempotent and keeps the *original* rationale rather than the newer one; a qualifying discovery routes through the exact same generator as an internal candidate and produces a real scored recommendation; a candidate with a compelling-sounding but quantitatively failing rationale (`predicted_probability=0.10`) is still `NOT_QUALIFIED` with `failed_criteria=["model_probability"]` and zero `Prediction` rows created — proving the rationale text cannot buy qualification; a stock never scanned raises `DiscoveryCandidateNotInScanError` rather than fabricating a candidate; a scan-excluded stock raises the ordinary `CandidateNotEligibleError`, unmodified; routing the same discovery twice is idempotent (one `Prediction` row); and two otherwise-identical scan candidates differing only in rationale text produce the identical outcome, directly proving the rationale never enters the decision.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] External discovery candidates use the same quantitative evaluation path as internal candidates (identical call to `generate_recommendation_for_candidate`).
- [x] Discovery rationale is clearly separated from quantitative evidence (`DiscoveryRecord.rationale` is never read by any consensus/scoring/horizon code; proven directly by `test_rationale_text_never_influences_the_generated_recommendation`).
- [x] ChatGPT cannot bypass positive-consensus qualification (proven by `test_compelling_rationale_cannot_bypass_positive_consensus_qualification`).
- [x] Non-qualifying candidates are explicitly recorded as `NOT MATCHING POSITIVE CONSENSUS` where applicable (via `OUTCOME_NOT_QUALIFIED`, this pipeline's applicable equivalent — see Design Decisions).
- [x] Discovery provenance is traceable (`DiscoveryRecord` rows, linked to their `RecommendationGeneration` once routed).
- [x] Tests demonstrate bypass prevention.

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip. The choice to treat `OUTCOME_NOT_QUALIFIED` as the applicable equivalent of the watchlist path's `NOT MATCHING POSITIVE CONSENSUS` label, given the scope's explicit requirement for the fuller M1.9/M1.10 pipeline that only M1.13's generator provides, is a documented design decision open to reviewer adjustment. Per the user's 2026-08-20 standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

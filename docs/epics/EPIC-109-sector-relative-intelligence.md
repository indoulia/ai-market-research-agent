# EPIC-109 — Sector & Peer Relative Intelligence

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Evaluate stocks relative to their sector, industry and comparable peers so positive opportunities reflect relative strength and not only absolute movement.

## Scope
- Build sector/industry peer groups.
- Measure relative momentum, valuation, fundamentals and event impact where data permits.
- Compare prediction performance against peer-relative context.
- Feed relative evidence into ranking and Trust Score.
- Preserve point-in-time peer membership.

## Dependencies
EPIC-029, EPIC-096, EPIC-099, EPIC-101.

## Completion Report

**Status:** DONE — merged to main via PR #182 (`a9c60aa`).

**Implementation:**
- `app/sector_relative_intelligence.py`: a new, versioned (`SECTOR_RELATIVE_VERSION = "SRI-001"`) module.
- **Build sector/industry peer groups / preserve point-in-time peer membership:** `assess_sector_relative_strength` builds the peer group from `ScanCandidate` rows in the exact same `DailyCandidateScan` as the target prediction's own candidacy, sharing `Stock.sector` — genuinely same-point-in-time, not merely same-sector. `peer_stock_ids` and every derived value are frozen into the immutable assessment row, the same posture EPIC-029's `DiscoverySegment` already established for sector/market-cap classification surviving a later `Stock.sector` reclassification unaffected.
- **Measure relative momentum where data permits:** a z-score of the target's `sma20_distance` against the peer group's own mean/stdev, verdict `STRONGER_THAN_PEERS`/`WEAKER_THAN_PEERS`/`IN_LINE_WITH_PEERS`/`INSUFFICIENT_PEER_GROUP` (below `MIN_PEER_GROUP_SIZE = 3`, or a zero-variance peer group that can't be standardized against).
- **Relative valuation/fundamentals and event impact are honestly out of scope for this version** — named explicitly in the module docstring (no guaranteed same-date peer coverage in this platform's fundamental data yet) rather than fabricated.
- **Compare prediction performance against peer-relative context:** `compare_sector_performance` reuses EPIC-011's/`trust_report`'s own `VERDICT_OK`/`VERDICT_WEAK`/`VERDICT_INSUFFICIENT_SAMPLE` vocabulary and `WEAKNESS_MARGIN`, comparing a sector's success rate against the platform-wide baseline within a window — the same always-fresh "report" posture as EPIC-088/EPIC-099/EPIC-102/EPIC-108.
- **Feed relative evidence into ranking and Trust Score:** propose-only — no write path to `Prediction`, `PredictionTrustScore`, or any ranking table.
- New tables `sector_relative_assessments` and `sector_performance_reports` (migration `0084_sector_relative_intelligence.py`).

**Tests:** `tests/test_sector_relative_intelligence.py` (9 tests) — insufficient peer group, stronger/weaker/in-line-with-peers verdicts (z-score math verified by hand), a different-sector candidate correctly excluded from the peer group, idempotency, and sector-performance insufficient-sample/weak/ok cases.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_sector_relative_intelligence.py -q` → `9 passed`
- `python -m pytest -q` (full suite) → `1050 passed`
- `python -m alembic heads` → single head `0084_sector_relative (head)`, chain resolves cleanly

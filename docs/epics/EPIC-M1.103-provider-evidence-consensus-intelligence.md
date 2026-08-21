# EPIC-M1.103 — Provider & Evidence Consensus Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Use independent provider and evidence agreement/disagreement as an explicit signal of prediction reliability, data quality and Trust Score.

## Scope
- Measure agreement across AI, market-data, fundamental, news and event providers where multiple sources exist.
- Distinguish independent corroboration from duplicated/syndicated evidence.
- Detect material provider disagreement.
- Weight consensus by provider reliability, freshness and source authority.
- Preserve provider/evidence consensus snapshots.
- Feed validated consensus signals into Trust Score and recommendation eligibility.
- Never allow provider majority to override an authoritative source without policy justification.

## Acceptance Criteria
- Provider/evidence agreement is measurable.
- Duplicate sources do not falsely increase consensus.
- Material disagreement is surfaced and auditable.
- Consensus can affect Trust Score through explicit policy.
- Historical consensus remains immutable.

## Dependencies
Previous: M1.90, M1.93, M1.102.
Next: Future prediction-quality enhancements.

## Completion Report

**Status:** VALIDATING (implemented, tests passing, PR open)

**Implementation:**
- `app/provider_evidence_consensus.py`: a new, versioned (`CONSENSUS_VERSION = "PEC-001"`) module. M1.65 explicitly documented that no real second source existed for the same fact when it was written; M1.91 changed that for fundamental (`alpha-vantage` alongside `yahoo-finance`) and news/event (`finnhub` alongside `yahoo-finance`) data — this is the first module to actually compare what two independent providers reported about the same fact.
- **Measure agreement across providers / weight by reliability, freshness and source authority:** `assess_fundamental_consensus` dedupes each `FundamentalDataRecord` source to its most-recently-fetched `eps` for one `(stock_id, period_end_date)` first (AC: "duplicate sources do not falsely increase consensus" — a re-fetched source never counts twice, proven directly by `test_dedupes_to_latest_fetch_per_source`), then weights each remaining source by a fixed 3-tier freshness decay, M1.93's own per-provider reliability verdict (equal weight when unmeasured, never zero), and a fixed `SOURCE_AUTHORITY_TIER` (currently equal for every real provider — none is a primary/regulatory source in this platform today, an honest forward-compatible constant).
- **Detect material provider disagreement:** `max_relative_deviation` against the weighted mean, thresholded at `STRONG_AGREEMENT_THRESHOLD`/`MATERIAL_DISAGREEMENT_THRESHOLD`; `INSUFFICIENT_SOURCES` when fewer than two distinct providers reported.
- **Distinguish independent corroboration from duplicated/syndicated evidence:** `classify_news_event_consensus` groups `NewsEventRecord`s within a fixed syndication window by normalized headline — two providers with the *same* normalized headline is `SYNDICATED_DUPLICATE` (one story, multiple wires); two providers with *different* headlines is `INDEPENDENT_CORROBORATION`. Counting distinct headlines, not distinct source rows, is what keeps a re-syndicated story from inflating the corroboration signal.
- **Market-data agreement is explicitly out of scope, honestly:** `MarketPrice`'s `(stock_id, timestamp)` uniqueness constraint (M1.3) means provider disagreement on a daily candle is already resolved/deduped at ingestion — there is no persisted second candle to compare, named in the module docstring rather than fabricated.
- **Never allow provider majority to override an authoritative source without policy justification (AC):** holds structurally — `SOURCE_AUTHORITY_TIER` is a fixed weight *input* to the consensus mean, never a vote-count override, and there is currently no higher-authority source configured to override in the first place.
- **Feed validated consensus signals into Trust Score / preserve consensus snapshots:** `trust_reduction_recommended` on the fundamental assessment is a propose-only signal (no write path to `PredictionTrustScore`/`TrustControlDecision`), the same posture M1.101/M1.102 established; both assessment types are new immutable tables (migration `0078_provider_evidence_consensus.py`).

**Tests:** `tests/test_provider_evidence_consensus.py` (9 tests) — insufficient-sources/strong-consensus/material-disagreement fundamental verdicts, per-source dedup, idempotency, and single-source/syndicated-duplicate/independent-corroboration/outside-window news verdicts.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_provider_evidence_consensus.py -q` → `9 passed`
- `python -m pytest -q` (full suite) → `973 passed`
- `python -m alembic heads` → single head `0078_provider_consensus (head)`, chain resolves cleanly

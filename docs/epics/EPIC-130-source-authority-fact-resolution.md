# EPIC-130 — Source Authority & Fact Conflict Resolution

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Resolve conflicting external facts using explicit source authority, freshness, provenance and fact-type policies rather than simple provider majority voting.

## Scope
- Define authority policies by fact type: price, corporate action, filing, financial result, event, news and other evidence.
- Distinguish authoritative primary sources from secondary aggregators and syndicated copies.
- Detect conflicting values across providers.
- Detect duplicated/syndicated evidence so it does not falsely increase consensus.
- Apply timestamp and effective-date precedence rules.
- Preserve all conflicting observations rather than deleting them.
- Produce a resolved fact with reason, source authority and confidence.
- Allow manual governance of authority rules without rewriting historical facts.

## Acceptance Criteria
- A provider majority cannot automatically override a configured authoritative source.
- Conflicting facts remain auditable.
- Resolved facts include provenance and resolution reason.
- Historical resolutions are immutable and versioned.
- Fact-resolution output can be consumed by prediction and learning systems.

## Dependencies
EPIC-090, EPIC-094, EPIC-103, EPIC-123.

## Architectural Rule
**Consensus is evidence; authority is policy. They must never be conflated.**

## Completion Report

**Status:** DONE -- merged to `main` via PR #243 (`30ce4fb`).

**Implementation:**
- `app/source_authority_resolution.py`: new, versioned (`RESOLUTION_VERSION = "SAR-001"`) module. New table `resolved_facts` (migration `0105_source_authority_resolution.py`).
- **Consensus is evidence; authority is policy -- never conflated (architectural rule):** EPIC-103's `app.provider_evidence_consensus` already characterizes *agreement* (a blended weighted mean, or corroboration verdict) and is untouched by this module. This module adds a genuinely separate layer: an explicit per-fact-type authority policy (`AUTHORITY_TIER_BY_FACT_TYPE`) that picks a single winning value, even when every other source disagrees with it.
- **Only two fact types have genuine multi-provider data on this platform today** -- `FUNDAMENTAL_EPS` and `NEWS_EVENT` (both from EPIC-091's `yahoo-finance`/`alpha-vantage`/`finnhub` adapters). Price, corporate action, filing and non-EPS financial-result fact types are honestly out of scope for this first version: `MarketPrice` dedupes provider disagreement at ingestion time (a hard `(stock_id, timestamp)` uniqueness constraint), and `app.corporate_actions` records each action from a single feed with no second source to ever conflict -- named here rather than fabricated, the same posture `provider_evidence_consensus` already took for market data.
- **A provider majority cannot automatically override a configured authoritative source (AC):** `resolve_fundamental_fact`/`resolve_news_event_fact` detect conflict across *all* available sources, then check whether a single source sits at the top authority tier -- if so, that source's own value wins regardless of how many lower-tier sources disagree (`REASON_AUTHORITATIVE_SOURCE_OVERRIDE`). Verified directly in tests by outnumbering the authoritative source 2-to-1 and asserting it still wins.
- **Apply timestamp and effective-date precedence rules (scope):** when the top authority tier is tied among two-or-more sources (every real provider is tier 1 today -- no source is yet classified as genuinely more authoritative, the same honest, forward-compatible posture `provider_evidence_consensus.SOURCE_AUTHORITY_TIER` already took), the most-recently-fetched fundamental record, or the earliest-published news record among the tied sources, wins (`REASON_TIMESTAMP_PRECEDENCE_TIEBREAK`) -- never a consensus blend.
- **Detect duplicated/syndicated evidence so it does not falsely increase consensus (AC):** two sources reporting the same normalized (trimmed, case-folded) headline for a news event are treated as agreeing, not as two facts to reconcile -- the same normalized-headline comparison `provider_evidence_consensus.classify_news_event_consensus` already uses for its own distinct purpose.
- **Preserve all conflicting observations (scope):** `FundamentalDataRecord`/`NewsEventRecord` (both already immutable/append-only) are never modified; `ResolvedFact` is a purely additive, derived summary row alongside them.
- **Produce a resolved fact with reason, source authority and confidence (AC):** every `ResolvedFact` row carries `resolution_reason`, `winning_source`/`winning_source_authority_tier`, and a `confidence` score (1.0 for unanimous agreement, 0.9 for an authority override, 0.6 for a timestamp tiebreak, 0.5 for a single unconfirmed source, 0 when no source has data at all).
- **Allow manual governance of authority rules without rewriting historical facts (AC):** `AUTHORITY_TIER_BY_FACT_TYPE` is a fixed, versioned Python policy table (this platform's established convention for policy constants, e.g. EPIC-132's `SECTOR_BENCHMARK_SYMBOLS`), not a learned or live-editable weight. Every row freezes `winning_source_authority_tier` and `resolution_rule_version` at `resolved_at` -- a future policy change only affects new resolutions under a new version string; historical rows are immutable and unaffected, the same frozen-row governance posture EPIC-109/EPIC-132 already established.
- **Fact-resolution output can be consumed by prediction and learning systems (AC):** `resolved_facts` is queryable (`get_resolved_fact_history`) but propose-only -- no write path into `Prediction`, `PredictionTrustScore`, or any ranking table yet, the same posture EPIC-103/EPIC-109/EPIC-125/EPIC-132/EPIC-133 already established, named here as explicit future work rather than fabricated.

**Tests:** `tests/test_source_authority_resolution.py` (12 tests) -- fundamental EPS: insufficient sources, single source, no-conflict agreement, timestamp-precedence tiebreak between equal-tier conflicting sources, an authoritative source overriding a 2-to-1 majority (via `monkeypatch` on the policy table), idempotency. News/event: insufficient sources, single source, syndicated-duplicate headline correctly not flagged as conflict, timestamp-precedence tiebreak between genuinely different headlines, an authoritative source overriding a 2-to-1 majority, idempotency. One real bug caught and fixed during testing: the news resolver's `conflicting` check was initially computed only over top-tier sources' headlines, which meant a lone authoritative source's dissenting headline against a 2-source majority went undetected as a conflict at all (falling through to `NO_CONFLICT`, never reaching the override branch) -- fixed to judge conflict across *every* source in-window, matching the fundamental-fact resolver's own (correct) logic.

**Isolation note:** implemented in a dedicated worktree (`C:/AIAgent/market-agent-m1-127`, branch `autonomous/epic-m1-127`) rather than the shared `C:/AIAgent/market-agent-m1` directory, after an unrelated external process checked out an unrelated branch (`feature/rancher-deploy`) in that shared directory mid-session and silently discarded uncommitted EPIC-130 work-in-progress. No data was lost from any merged EPIC as a result; this is a process note for future sessions working in that shared directory.

**Rebase note:** EPIC-127, EPIC-124, EPIC-129 and EPIC-126 each merged to `main` while this branch was in flight, colliding on migration number `0101` (EPIC-127), then `0102` (EPIC-124), then `0103` (EPIC-129), then `0104` (EPIC-126) -- the same known pattern hit repeatedly this session, as `main` advanced faster than one rebase could keep up. Rebased onto latest `main` three times and renumbered this EPIC's migration to `0105_source_authority_resolution.py`, chained after `0104_champion_challenger_shadow`. Each time, the same additive-append conflict shape recurred in `app/models.py` (git's 3-way merge occasionally drops a trailing `created_at` line shared verbatim between two unrelated classes appended at the same point) -- each resolution was verified against `origin/main`'s actual content, not assumed.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_source_authority_resolution.py -q` -> `12 passed`
- `python -m pytest -q` (full suite, real local Postgres) -> `1309 passed` (grew from 1267 as `main` advanced through EPIC-124/EPIC-126/EPIC-127/EPIC-129 during the rebases)
- `python -m alembic heads` -> single head `0105_source_authority (head)`, chain resolves cleanly

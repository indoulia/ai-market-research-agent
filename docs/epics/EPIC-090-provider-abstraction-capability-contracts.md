# EPIC-090 — Provider Abstraction & Capability Contracts

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Make every external-world capability in MRA provider-based so domain and recommendation logic never depends directly on a specific vendor.

## Scope
- Define provider contracts for AI/discovery, market data, fundamentals, news, events and other external information sources.
- Separate provider adapters from domain/business logic.
- Define normalized capability-level request/response contracts.
- Preserve provenance, timestamps, provider identity and version metadata.
- Support provider-specific failures without leaking vendor types into domain code.
- Define capability availability and health contracts.
- Require at least three interchangeable implementation slots per provider capability at architecture/test level.
- Add contract and substitution tests.

## Acceptance Criteria
- No domain service directly calls a named external provider SDK/API.
- Provider implementations are replaceable behind stable contracts.
- Provider metadata and provenance are preserved.
- A provider can be disabled without changing recommendation/business logic.
- Contract tests prove interchangeable implementations.

## Dependencies
Previous: EPIC-075, EPIC-077, EPIC-030.
Next: EPIC-091.

## Architectural Invariant
**All external-world access MUST go through provider contracts.** Direct vendor coupling in domain/business logic is prohibited.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-090

### Branch

autonomous/epic-m1-90, branched cleanly from `main` (the declared dependencies -- EPIC-075, EPIC-077, EPIC-030 -- are already merged).

### Objective

Make every external-world capability in this platform provider-based so domain and recommendation logic never depends directly on a specific vendor.

### Design

This is deliberately a contracts-only EPIC -- it introduces no new persisted state and no registry (that is EPIC-092's own, later job). `app/provider_contracts.py` formalizes a pattern this platform already followed informally from EPIC-003 onward: a `typing.Protocol` provider boundary, a `source` class attribute, a `fetch_*` method, and a provider-agnostic orchestration function that only depends on the Protocol. Every existing adapter (`YahooFinanceClient`, `UpstoxClient`, `YahooFundamentalsClient`, `YahooNewsClient`) is retrofitted with two additional, uniform class attributes (`capability`, `version`), additive and backward compatible -- `source` is unchanged, and no existing test needed modification.

### AI/Discovery Has No Real Provider Today, Honestly

`app.discovery.record_discovery` accepts an externally-supplied rationale string; no adapter in this codebase calls an LLM API. Rather than fabricate one, `CAPABILITY_AI_DISCOVERY` and `AIDiscoveryProvider` are defined as a real, usable contract with zero real implementations -- the same honest, forward-compatible posture EPIC-030 held for `DATA_TYPE_FUNDAMENTAL`/`DATA_TYPE_NEWS_EVENT` before EPIC-075/EPIC-077 gave them real ones.

### Three Interchangeable Slots, At Test Level Where Real Ones Don't Exist

MARKET_DATA already has two real, independent adapters (Yahoo, Upstox); `tests/test_provider_contracts.py` adds a third, in-memory fake to every capability -- including the zero-real-adapter AI_DISCOVERY capability -- and proves the same domain code path accepts all of them interchangeably, exactly as the scope's own "at architecture/test level" wording permits.

### Vendor Errors Never Leak Into Domain Code

`test_provider_specific_errors_never_leak_out_of_fundamentals_ingestion` and its news-ingestion counterpart prove a vendor-specific exception type (`YahooFundamentalsError`/`YahooNewsError`) is always caught by the domain ingestion function and converted into a generic, already-established `DataFetchAttempt` failure record -- never propagated as a bare, vendor-typed exception.

### A Provider Can Be Swapped Without Touching Domain Logic

`test_domain_ingestion_is_unchanged_when_the_fundamentals_provider_is_swapped` and its news counterpart call the exact same, unmodified `ingest_fundamental_data`/`ingest_news_events` functions with two different fake providers and get correctly-attributed results from each -- proving AC "provider implementations are replaceable behind stable contracts" and "a provider can be disabled without changing recommendation/business logic" directly, not by inspection alone.

### Health And Metadata Contracts

`ProviderHealthStatus`/`check_provider_health` (scope: "define capability availability and health contracts") honestly report "no health check implemented; assumed available" for providers that don't implement one, rather than fabricating a healthy status; `get_provider_metadata`/`verify_provider_contract` raise a domain-level `ProviderContractViolationError` rather than a bare `AttributeError` when a provider is malformed.

### Files Changed

- `app/provider_contracts.py` — new: capability constants, `ProviderMetadata`, `ProviderHealthStatus`, `HealthCheckable`, `AIDiscoveryProvider`, `get_provider_metadata`, `verify_provider_contract`, `check_provider_health`.
- `app/market_data/upstox.py`, `app/market_data/yahoo.py`, `app/fundamental_data/yahoo.py`, `app/news_data/yahoo.py` — additive `capability`/`version` class attributes.
- `tests/test_provider_contracts.py` — new: 21 tests.
- `docs/epics/EPIC-090-provider-abstraction-capability-contracts.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_provider_contracts.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0066_usefulness_assessment` -- unchanged; this EPIC adds no persisted schema)

### Test Results

- `pytest -q`: **772 passed, 0 failed** (no regressions from the additive attribute retrofit).
- `test_provider_contracts.py`: **21 passed** — every real adapter (Yahoo market data, Upstox, Yahoo fundamentals, Yahoo news) and every fake test double satisfies the shared contract; three interchangeable slots exist per capability, including the zero-real-adapter AI-discovery capability; a wrong-capability claim and a malformed provider are both correctly rejected with a domain-level error, never a bare `AttributeError`; health-check contract works for both health-aware and health-unaware providers; domain ingestion produces correctly-attributed results when the concrete fundamentals/news provider is swapped, with zero changes to the ingestion functions themselves; vendor-specific errors never escape ingestion as anything other than a generic failed fetch-attempt record.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).

### Acceptance Criteria

- [x] No domain service directly calls a named external provider SDK/API (verified: `app/market_data/ingest.py`, `app/fundamental_data/ingest.py`, `app/news_data/ingest.py` import no vendor SDK).
- [x] Provider implementations are replaceable behind stable contracts (proven by test).
- [x] Provider metadata and provenance are preserved (`ProviderMetadata`/`get_provider_metadata`).
- [x] A provider can be disabled without changing recommendation/business logic (proven by test).
- [x] Contract tests prove interchangeable implementations (21 tests across all four capabilities).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a direct proof that swapping a concrete provider requires zero changes to the domain ingestion functions that consume it. This EPIC retrofits EPIC-003/EPIC-075/EPIC-077's already-built adapters additively rather than rewriting any of them, and honestly declares the AI/discovery capability contract-only where this platform has no real implementation, matching the same posture EPIC-030 held for fundamentals/news before real pipelines existed. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

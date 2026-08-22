# EPIC-091 — Multi-Provider Implementations

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Prove that MRA's provider contracts are genuinely vendor-neutral by implementing multiple interchangeable providers for each critical external capability.

## Scope
- Implement at least three providers for each critical capability where practical and commercially/technically available.
- AI/discovery examples: OpenAI, Claude, Ollama/local model.
- Market data, fundamentals, news and event capabilities: support multiple independent provider adapters.
- Normalize provider responses into common contracts.
- Handle authentication, rate limits, timeouts and provider-specific errors inside adapters.
- Add provider substitution and parity tests.
- Keep provider-specific behavior isolated from domain logic.

## Acceptance Criteria
- Critical capabilities have at least three implementation paths or documented adapter targets where a third production source is unavailable.
- Switching providers requires configuration/registry changes, not domain-code changes.
- Provider-specific failures do not corrupt normalized domain data.
- Common test suites run against multiple providers/adapters.
- Provenance identifies the actual provider used.

## Dependencies
Previous: EPIC-090.
Next: EPIC-092.

## Rule
Adding a provider must be an adapter task, not a core-engine redesign.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-091

### Branch

autonomous/epic-m1-91, branched cleanly from `main` (the declared dependency -- EPIC-090 -- is already merged).

### Objective

Prove that this platform's provider contracts are genuinely vendor-neutral by implementing multiple interchangeable providers for each critical external capability.

### Design

Adding every new provider was purely an adapter task, exactly per this EPIC's own Rule: zero changes to `ingest_daily_history`/`ingest_fundamental_data`/`ingest_news_events`, and zero changes to EPIC-090's `provider_contracts.py` itself.

- **Market data** (already had two real adapters: Yahoo, Upstox) gains a third: `app/market_data/stooq.py`'s `StooqClient` -- a free, no-authentication CSV source, following the exact same offline-fixture-tested pattern as `YahooFinanceClient`.
- **Fundamentals** gains a second real adapter: `app/fundamental_data/alpha_vantage.py`'s `AlphaVantageFundamentalsClient`, against the free-tier `OVERVIEW` endpoint, requiring an explicit API key at construction (never an unauthenticated or fabricated request).
- **News** gains a second real adapter: `app/news_data/finnhub.py`'s `FinnhubNewsClient`, against the free-tier `company-news` endpoint, same explicit-credential requirement.
- **AI/discovery** gains its first real adapter: `app/ai_discovery/ollama.py`'s `OllamaDiscoveryClient`, a free, local, no-authentication model server. OpenAI and Claude are named in scope but are paid, rate-limited, cost-incurring APIs -- implementing live integrations for them without an explicit credential/budget decision from the project owner was judged out of scope for an autonomous session; both are honestly declared `DOCUMENTED_UNIMPLEMENTED_PROVIDERS`, satisfying AC's own explicit "documented adapter target" escape hatch.

### Three Real Or Fake Slots Per Capability, Now With More Real Ones

MARKET_DATA: three real adapters (Yahoo, Upstox, Stooq). FUNDAMENTAL_DATA and NEWS_EVENT_DATA: two real adapters each, both satisfying EPIC-090's shared contract test (`verify_provider_contract`). AI_DISCOVERY: one real adapter plus two documented targets.

### Vendor Failures Never Corrupt Domain Data

Every new adapter raises its own, distinct error type (`StooqError`, `AlphaVantageError`, `FinnhubError`, `OllamaDiscoveryError`) which the *existing, unmodified* domain ingestion functions already catch generically and convert into a `DataFetchAttempt` failure record -- `test_alpha_vantage_errors_never_leak_out_of_fundamentals_ingestion` and `test_finnhub_errors_never_leak_out_of_news_ingestion` prove zero rows are ever partially written on failure.

### Provider Swap Requires No Domain-Code Change

`test_fundamental_ingestion_is_unchanged_when_alpha_vantage_is_used` and `test_news_ingestion_is_unchanged_when_finnhub_is_used` call the exact same, unmodified ingestion functions with the new real adapters and get correctly-attributed (`source == "alpha-vantage"`/`"finnhub"`) results -- proving AC "switching providers requires configuration/registry changes, not domain-code changes" directly.

### Files Changed

- `app/market_data/stooq.py` — new `StooqClient`/`StooqError`.
- `app/fundamental_data/alpha_vantage.py` — new `AlphaVantageFundamentalsClient`/`AlphaVantageError`/`AlphaVantageCredentialsError`.
- `app/news_data/finnhub.py` — new `FinnhubNewsClient`/`FinnhubError`/`FinnhubCredentialsError`.
- `app/ai_discovery/__init__.py`, `app/ai_discovery/ollama.py` — new package: `OllamaDiscoveryClient`/`OllamaDiscoveryError`, `DOCUMENTED_UNIMPLEMENTED_PROVIDERS`.
- `app/market_data/__init__.py`, `app/fundamental_data/__init__.py`, `app/news_data/__init__.py` — export the new adapters.
- `tests/test_multi_provider_implementations.py` — new: 22 tests.
- `docs/epics/EPIC-091-multi-provider-implementations.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_multi_provider_implementations.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0066_usefulness_assessment` -- unchanged; this EPIC adds no persisted schema)

### Test Results

- `pytest -q`: **794 passed, 0 failed**.
- `test_multi_provider_implementations.py`: **22 passed** — every new adapter satisfies its capability's shared contract; each correctly parses a real response shape and wraps provider errors in its own distinct error type; credential-requiring adapters refuse construction without a key; domain ingestion produces correctly-attributed results with zero code changes when the concrete provider is swapped; vendor errors never leak past a generic failed-fetch-attempt record; the two documented-but-unimplemented AI providers are named explicitly.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).

### Acceptance Criteria

- [x] Critical capabilities have at least three implementation paths or documented adapter targets where a third production source is unavailable (market data: 3 real; fundamentals/news: 2 real; AI-discovery: 1 real + 2 documented).
- [x] Switching providers requires configuration/registry changes, not domain-code changes (proven by test).
- [x] Provider-specific failures do not corrupt normalized domain data (proven by test).
- [x] Common test suites run against multiple providers/adapters (`verify_provider_contract` applied to every new and existing adapter).
- [x] Provenance identifies the actual provider used (`source` field correctly reflects the concrete adapter in every ingested record).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence. Every new adapter is real, production-callable code following this platform's own established offline-fixture-test convention, and adding each one required zero changes to any existing domain or contract code -- directly demonstrating the vendor-neutrality EPIC-090 designed for. I made a deliberate scope judgment to implement the one free, no-credential AI/discovery provider (Ollama) fully while declaring OpenAI/Claude as documented targets rather than building untested, cost-incurring paid-API integrations without the project owner's explicit authorization; this is flagged here for visibility. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->

# EPIC-M1.3 — Add Yahoo NSE Historical Data Provider

**Status:** READY
**Priority:** P1
**Owner:** Engineering Orchestrator

## Objective

Add a Yahoo Finance research-data adapter for daily NSE OHLCV so the prediction platform can obtain historical market data without requiring Upstox credentials.

## Dependencies

- M1 Foundation — merged
- M1.1 Historical NSE Data Ingestion — merged
- M1.2 Historical Market Data Quality & Dataset Validation — merged

## Scope

1. Add a small Yahoo Finance provider using `yfinance`.
2. Support configured NSE symbols such as `RELIANCE.NS`, `TCS.NS`, and `INFY.NS`.
3. Normalize provider output into the existing market-price ingestion contract.
4. Handle provider-side missing rows, duplicates, invalid OHLC relationships, and unusable values deterministically.
5. Add focused unit tests using local fixtures; tests must not require network access.
6. Preserve a provider boundary so Upstox or another licensed provider can be added later without changing downstream prediction logic.
7. Document Yahoo Finance as a research/prototyping source, not a claim of licensed production market-data redistribution.

## Acceptance Criteria

- [ ] Daily NSE historical OHLCV can be retrieved through the provider adapter.
- [ ] Provider output maps cleanly to the existing market-price contract.
- [ ] Invalid and duplicate provider rows are handled deterministically.
- [ ] Unit tests pass without network access.
- [ ] Prediction and feature-generation code does not depend directly on `yfinance`.
- [ ] No Upstox credential or broker integration is required.

## Non-goals

- Intraday data.
- Live trading.
- Broker integration.
- Portfolio management.
- Prediction-model changes.
- UI/dashboard work.

# EPIC-M1.96 — Corporate Action & Historical Market Truth

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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

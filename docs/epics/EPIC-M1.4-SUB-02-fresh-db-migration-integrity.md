# EPIC-M1.4-SUB-02 — Fresh Database Migration Integrity

**Parent EPIC:** EPIC-M1.4  
**Status:** APPROVED  
**Execution Status:** BLOCKED  
**Priority:** P1

## Context

The M1.4 completion report identified a pre-existing failure in `migrations/versions/0003_market_price_dedupe.py`: a relation/index name conflicts with the unique constraint created by `0001_initial`. This prevents a clean `alembic upgrade head` on a fresh database.

M1.4 has already merged via PR #10. This remediation is independent of PR #10 and MUST be implemented as a new branch/PR against current `main`.

## Objective

Make a completely fresh PostgreSQL database migrate successfully to the current Alembic head without manually stamping past a broken migration.

## Scope

1. Inspect the migration chain and identify the exact `0003` conflict.
2. Apply the smallest safe migration-history correction.
3. Preserve the intended `market_prices` uniqueness behavior.
4. Validate upgrade from an empty database to head.
5. Validate downgrade/upgrade behavior where appropriate.
6. Add migration validation to automated tests/CI if practical and bounded.

## Non-goals

- General database redesign.
- Changing recommendation behavior.
- Rewriting unrelated migrations.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Fresh PostgreSQL database can run `alembic upgrade head` without manual stamping/skipping.
- [ ] Intended `market_prices` uniqueness behavior remains intact.
- [ ] Migration history remains coherent.
- [ ] Relevant migration validation is automated where practical.
- [ ] Existing application tests remain green.
- [ ] Completion Report is populated in this EPIC before PR review.

## Dependencies

- EPIC-M1.4-SUB-01 should be completed first to preserve one-EPIC-at-a-time execution.

## Execution Rules

Do not execute while `Execution Status: BLOCKED`. After SUB-01 merges successfully, ChatGPT will authorize this EPIC by changing its execution status to `READY_FOR_EXECUTION`.

## Completion Report

<!-- Claude: populate after implementation. Never erase review history. -->

## Review History

### Finding Origin

Discovered during EPIC-M1.4 implementation validation and recorded in PR #10's completion report. PR #10 has since merged.

### Review State

Awaiting execution authorization after SUB-01.

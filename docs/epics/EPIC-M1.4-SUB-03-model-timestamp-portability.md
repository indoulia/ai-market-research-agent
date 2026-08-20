# EPIC-M1.4-SUB-03 — Model Timestamp Portability

**Parent EPIC:** EPIC-M1.4  
**Status:** APPROVED  
**Execution Status:** BLOCKED  
**Priority:** P2

## Context

The M1.4 completion report identified literal `server_default="now()"` values in several SQLAlchemy models. This is dialect-fragile and prevents clean SQLite fixture use for affected models.

M1.4 has already merged via PR #10. This remediation is independent of PR #10 and MUST be implemented as a new branch/PR against current `main`.

## Objective

Make model timestamp defaults dialect-portable without changing PostgreSQL behavior or broadening the work into unrelated model refactoring.

## Scope

1. Identify affected model timestamp defaults.
2. Replace literal/dialect-fragile defaults with the repository's appropriate SQLAlchemy expression.
3. Preserve migration/schema semantics.
4. Add focused tests for affected model timestamp behavior under the repository's supported test dialects.
5. Keep the change minimal and isolated.

## Non-goals

- General model refactoring.
- Recommendation logic changes.
- Database migration redesign beyond what is strictly required.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Affected model timestamp defaults are dialect-portable.
- [ ] PostgreSQL behavior remains correct.
- [ ] SQLite fixture behavior works without special workarounds.
- [ ] Tests cover affected models.
- [ ] No unrelated model behavior changes.
- [ ] Completion Report is populated in this EPIC before PR review.

## Dependencies

- EPIC-M1.4-SUB-01 should be completed first to preserve one-EPIC-at-a-time execution.
- EPIC-M1.4-SUB-02 should be completed before this EPIC unless ChatGPT explicitly changes the ordering.

## Execution Rules

Do not execute while `Execution Status: BLOCKED`. ChatGPT will authorize execution after the prerequisite remediation work is complete.

## Completion Report

<!-- Claude: populate after implementation. Never erase review history. -->

## Review History

### Finding Origin

Discovered during EPIC-M1.4 implementation validation and recorded in PR #10's completion report. PR #10 has since merged.

### Review State

Awaiting execution authorization after prerequisites.

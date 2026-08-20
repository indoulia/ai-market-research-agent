# EPIC-M1.4-SUB-01 — Recommendation History Integrity

**Parent EPIC:** EPIC-M1.4  
**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P0

## Context

EPIC-M1.4 was implemented in PR #10 and was merged to `main` before ChatGPT's strict review. The implementation protects immutable recommendation fields through a SQLAlchemy `before_update` listener, but the review identified that this is an ORM-level guard rather than a persistence/database integrity boundary.

PR #10 is already merged. Therefore this remediation MUST NOT attempt to update PR #10. It must be implemented as a new branch and PR against the current `main`.

## Target

- Original implementation PR: **#10**
- Original branch: `autonomous/epic-m1-4`
- Remediation target: **current `main`**
- New implementation branch: Claude should create an `autonomous/epic-m1-4-sub-01` branch (or repository-equivalent naming).
- New PR: required.

## Objective

Strengthen recommendation-history integrity so the original recommendation fields cannot be silently modified through supported persistence paths beyond the specific ORM event listener.

## Scope

1. Define exactly which recommendation fields are immutable after issuance.
2. Enforce immutability at the persistence/database boundary appropriate to the repository's PostgreSQL architecture.
3. Keep outcome/status fields mutable for M1.5.
4. Add tests demonstrating that supported persistence paths cannot alter immutable recommendation fields.
5. Preserve the existing M1.4 API and data model unless a minimal change is required.
6. Update this EPIC's Completion Report on the implementation PR.

## Non-goals

- Rewriting M1.4.
- Creating a duplicate recommendation table.
- Implementing M1.5 outcome evaluation.
- Changing recommendation-generation logic.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Immutable recommendation fields are explicitly documented.
- [ ] Integrity is enforced at the persistence/database boundary, not solely by the existing ORM event listener.
- [ ] M1.5 can still update outcome/status fields without changing the original recommendation.
- [ ] Tests demonstrate the integrity protection through the supported persistence path.
- [ ] Existing M1.4 behavior remains compatible.
- [ ] New PR is based on current `main` and passes all required validation.
- [ ] Completion Report is populated in this EPIC before PR review.

## Execution Rules

- Work from current `origin/main`.
- Do not modify the already-merged PR #10 branch.
- Create a new remediation branch and PR.
- Do not merge until ChatGPT strict review passes.

## Completion Report

<!-- Claude: populate after implementation. Never erase review history. -->

## Review History

### Review 1 — REJECTED / REMEDIATION REQUIRED

Reviewer: ChatGPT  
Original PR: #10  
Original PR status: MERGED before strict review

Finding:

The implementation's immutability guarantee is enforced through a SQLAlchemy `before_update` listener. That is insufficient as the sole integrity boundary for a historical trust/evidence record.

Required remediation:

Move or supplement the guarantee at the persistence/database boundary while preserving mutable outcome/status fields.

**Resolution path:** New PR required because PR #10 has already merged.

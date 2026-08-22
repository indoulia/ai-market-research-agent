# EPIC-002 — Autonomous EPIC Engineering Loop

**Status:** PR_OPEN
**Priority:** P0
**Owner:** Engineering Orchestrator

## Objective

Create a repository-driven engineering loop in which a merge to `main` triggers a Codex worker, the worker discovers the highest-priority eligible `READY` EPIC under `docs/epics/`, implements it on a feature branch, validates it, and opens a pull request.

## Scope

1. Define a machine-readable EPIC lifecycle.
2. Define discovery and dependency rules.
3. Add repository-local Codex operating instructions.
4. Trigger Codex from a post-merge GitHub Actions event.
5. Give the worker repository write capability only through a feature branch and pull request workflow.
6. Record progress in the EPIC and an engineering log.
7. Prevent duplicate concurrent claims.
8. Escalate genuine product, architecture, credential, or security blockers instead of guessing.

## EPIC lifecycle

`DRAFT -> READY -> CLAIMED -> IN_PROGRESS -> VALIDATING -> PR_OPEN -> DONE`

Failure states:

`BLOCKED`, `FAILED`, `NEEDS_DECISION`

## Acceptance criteria

- [x] A merge into `main` can trigger the autonomous engineering workflow.
- [x] The workflow can run Codex non-interactively against the repository.
- [x] Codex reads repository-local instructions before acting.
- [x] Codex discovers only EPICs with `Status: READY` and satisfied dependencies.
- [x] Codex claims an EPIC before implementation and prevents duplicate claims through repository state.
- [x] Codex creates a feature branch and never pushes directly to `main`.
- [x] Codex runs the repository validation suite before opening a PR.
- [x] Codex updates EPIC status and records an auditable summary.
- [x] A blocked EPIC does not prevent unrelated eligible EPICs from being considered.
- [x] Secrets are obtained only from GitHub Actions secrets/environment and are never written to repository files.
- [x] The workflow has explicit least-privilege permissions and does not expose arbitrary PR/user text to shell commands.

## Non-goals

- Autonomous production deployment.
- Autonomous live trading.
- Autonomous changes to product direction.
- Automatic merging without repository branch protection and required checks.
- Automatic invention of architectural decisions when a decision is genuinely required.

## Implementation notes

Use the official `openai/codex-action` for GitHub Actions execution. Start with the workspace permission profile and explicit repository permissions. The worker prompt must instruct Codex to inspect `docs/epics/`, claim one eligible EPIC, implement it, validate it, and open a PR.

The merge event is a trigger, not the source of truth. The EPIC documents remain the engineering queue.

## Validation note

PR #3 contains the implementation. The post-merge workflow run is the final activation validation; until that event occurs this EPIC remains `PR_OPEN` rather than `DONE`.

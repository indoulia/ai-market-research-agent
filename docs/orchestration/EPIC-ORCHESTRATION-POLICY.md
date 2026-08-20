# EPIC Orchestration Policy

## Source of truth

The repository is the persistent engineering control plane. `docs/epics/` contains the executable roadmap. Chat conversations may propose or explain work, but implementation state must be reflected in the repository.

## Discovery

On each orchestration run:

1. Read all EPIC files under `docs/epics/`.
2. Ignore `DRAFT`, `DONE`, `BLOCKED`, `FAILED`, and `NEEDS_DECISION` unless explicitly instructed otherwise.
3. Consider only `READY` EPICs whose dependencies are satisfied by merged work.
4. Select the highest-priority eligible EPIC. If priority ties, select the lowest EPIC number.
5. Claim exactly one EPIC before modifying implementation files.

## Ownership

A worker must not implement the same EPIC concurrently with another worker. The claim must be observable in Git history/EPIC state. If a claim conflict is detected, stop without changing implementation files.

## Engineering rules

- Never push directly to `main`.
- Work from a feature branch created from current `main`.
- Read the relevant README, architecture documentation, existing tests, migrations, and neighboring EPICs before implementation.
- Prefer minimal, evidence-backed changes.
- Do not redesign approved architecture unless the EPIC explicitly requires it or implementation evidence demonstrates a defect.
- Add or update tests for changed behavior.
- Run the available validation suite before opening a PR.
- Keep documentation synchronized with implementation state.
- Never commit `.env`, access tokens, API keys, passwords, or other secrets.
- Do not perform live trading or production deployment unless a separate explicit authorization mechanism exists.

## Escalation

Mark an EPIC `NEEDS_DECISION` when implementation requires a product-direction choice, material architecture change, financial/trading authorization, or security exception. Mark it `BLOCKED` for missing dependencies or credentials. Do not invent a decision merely to keep the queue moving.

## Completion

A worker may mark an EPIC `DONE` only after the implementation PR has merged and the repository's required validation checks are green. The merge itself is the authoritative completion event.

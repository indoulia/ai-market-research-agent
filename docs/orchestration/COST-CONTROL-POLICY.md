# Autonomous Codex Cost-Control Policy

## Purpose

Prevent autonomous EPIC execution from becoming an unbounded OpenAI API workload.

## Initial policy

- One EPIC maximum per autonomous run.
- One autonomous worker at a time via GitHub Actions concurrency.
- Default model: `gpt-5.6-luna`.
- Default reasoning effort: `low`.
- Maximum wall-clock execution time: 30 minutes.
- No automatic model escalation.
- No automatic retry loop inside the same run.
- Stop once acceptance criteria and strongest practical validation pass.
- Stop and mark the EPIC `NEEDS_DECISION` when a product or architectural decision is required.
- Never perform live trading, financial transactions, or production deployment.

## Token/cost accounting

The workflow controls model, effort, concurrency, scope, and runtime. GitHub Actions does not expose OpenAI API token usage for the Codex Action as a reliable per-run budget gate, so this policy does **not** claim to enforce a dollar/token ceiling that the workflow cannot technically observe.

Actual OpenAI usage should be monitored at the OpenAI project/API-account level. If a hard API spend limit or usage alert is configured there, it remains the authoritative financial safety boundary.

## Operational rule

A failed or blocked EPIC must not cause an autonomous retry storm. The run should terminate and leave an explicit status/evidence trail for human review.

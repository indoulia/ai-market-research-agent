# EPIC-M1.91 — Multi-Provider Implementations

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
Previous: M1.90.
Next: M1.92.

## Rule
Adding a provider must be an adapter task, not a core-engine redesign.

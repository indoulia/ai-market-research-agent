from .ollama import OllamaDiscoveryClient, OllamaDiscoveryError

DOCUMENTED_UNIMPLEMENTED_PROVIDERS = ("openai", "anthropic-claude")
"""EPIC-M1.91 scope names OpenAI, Claude, and Ollama/local-model as
AI/discovery adapter targets. Implementing paid, rate-limited,
cost-incurring API integrations (OpenAI, Anthropic) without an explicit
credential/budget decision from the project owner is out of scope for
an autonomous session -- `OllamaDiscoveryClient` (a free, local,
no-authentication model server) is the one real, fully-functional
implementation here. OpenAI and Claude remain documented adapter
targets (AC: "... or documented adapter targets where a third
production source is unavailable") -- both would implement the exact
same `app.provider_contracts.AIDiscoveryProvider` contract
(`source`/`capability`/`version`/`discover_candidates`) with no changes
to any domain code, the moment API access is actually authorized."""

__all__ = ["DOCUMENTED_UNIMPLEMENTED_PROVIDERS", "OllamaDiscoveryClient", "OllamaDiscoveryError"]

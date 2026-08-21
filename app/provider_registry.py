"""EPIC-M1.92: centralized, capability-aware provider registration and
configuration so provider choice can change without modifying this
platform's business logic.

Composes rather than duplicates M1.90's contracts: registering a
provider always runs it through `verify_provider_contract` first (AC:
"invalid provider configurations fail clearly before use") -- this
module never re-implements credential/timeout/endpoint handling, which
already belongs to each concrete adapter's own constructor (M1.91's
`AlphaVantageFundamentalsClient(api_key=...)`, `FinnhubNewsClient(
api_key=...)`, etc.); the registry only holds already-configured
provider *instances* and decides which one to hand back for a given
capability.

Deliberately an instantiable class, not a hidden global singleton --
this platform's established convention is dependency injection via
function parameters everywhere (every `ingest_*` function already takes
its provider as an explicit argument); a `ProviderRegistry` instance is
itself just one more thing a caller constructs and passes around, never
an implicit ambient state domain code reaches for. "No business logic
contains provider-selection branches" (AC) is realized because
`resolve_provider` is the *only* place capability -> concrete-adapter
selection happens; a caller that uses the registry instead of importing
a concrete adapter directly never needs an if/elif chain to pick one.

"Preserve provider version/configuration identity in evidence and
prediction history" (scope) and "historical records preserve the
provider actually used" (AC) hold structurally, not as a new feature
here: every ingested record (`FundamentalDataRecord.source`, `NewsEventRecord.
source`, `MarketPrice.source`) already immutably captures which adapter
produced it (M1.72/M1.73/M1.3's own design) -- changing the registry's
active provider going forward can never rewrite what a past record says
produced it (AC: "safe configuration changes without rewriting
historical records").
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .provider_contracts import ALL_CAPABILITIES, ProviderContractViolationError, verify_provider_contract

PROVIDER_REGISTRY_VERSION = "PVR-001"

ROLE_PRIMARY = "PRIMARY"
ROLE_SECONDARY = "SECONDARY"
ROLE_OPTIONAL = "OPTIONAL"

_ROLE_PRIORITY = {ROLE_PRIMARY: 0, ROLE_SECONDARY: 1, ROLE_OPTIONAL: 2}
ALL_ROLES = (ROLE_PRIMARY, ROLE_SECONDARY, ROLE_OPTIONAL)


class InvalidProviderConfigurationError(ValueError):
    """Raised when a registration is invalid -- an unknown role, a
    duplicate (capability, role, provider_id), or a provider that fails
    M1.90's own contract check. Never a silent acceptance of a broken
    configuration."""


class NoProviderAvailableError(RuntimeError):
    """Raised when a capability has no enabled, registered provider --
    an honest failure, never a fabricated fallback."""


@dataclass(frozen=True)
class ProviderRegistration:
    capability: str
    role: str
    provider: object
    enabled: bool = True

    @property
    def provider_id(self) -> str:
        return self.provider.source


class ProviderRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, list[ProviderRegistration]] = {capability: [] for capability in ALL_CAPABILITIES}

    def register(self, *, capability: str, role: str, provider: object) -> ProviderRegistration:
        """Validates before accepting (AC: "invalid provider
        configurations fail clearly before use"): the role must be
        known, the provider must satisfy M1.90's contract for
        `capability`, and no other registration may already claim the
        same `(capability, role, provider_id)`."""
        if role not in ALL_ROLES:
            raise InvalidProviderConfigurationError(f"role must be one of {ALL_ROLES}, got {role!r}")
        try:
            verify_provider_contract(provider, expected_capability=capability)
        except ProviderContractViolationError as exc:
            raise InvalidProviderConfigurationError(str(exc)) from exc

        existing = self._registrations[capability]
        if any(r.role == role and r.provider_id == provider.source for r in existing):
            raise InvalidProviderConfigurationError(
                f"a {role} provider named {provider.source!r} is already registered for {capability}"
            )

        registration = ProviderRegistration(capability=capability, role=role, provider=provider)
        existing.append(registration)
        return registration

    def get_registrations(self, capability: str) -> tuple[ProviderRegistration, ...]:
        return tuple(self._registrations.get(capability, ()))

    def set_enabled(self, *, capability: str, provider_id: str, enabled: bool) -> ProviderRegistration:
        registrations = self._registrations.get(capability, [])
        for index, registration in enumerate(registrations):
            if registration.provider_id == provider_id:
                updated = replace(registration, enabled=enabled)
                registrations[index] = updated
                return updated
        raise InvalidProviderConfigurationError(f"no provider named {provider_id!r} registered for {capability}")

    def resolve_provider(self, capability: str, *, preferred_role: str | None = None) -> object:
        """Capability-level routing (scope: "support capability-level
        routing rather than one global provider"): returns the highest-
        priority enabled provider for `capability` -- `PRIMARY` before
        `SECONDARY` before `OPTIONAL` -- or the specific `preferred_role`
        if one is requested and enabled. Raises `NoProviderAvailableError`
        rather than silently returning nothing usable."""
        registrations = [r for r in self._registrations.get(capability, ()) if r.enabled]
        if preferred_role is not None:
            registrations = [r for r in registrations if r.role == preferred_role]
        if not registrations:
            raise NoProviderAvailableError(
                f"no enabled provider registered for capability {capability!r}"
                + (f" with role {preferred_role!r}" if preferred_role else "")
            )
        registrations.sort(key=lambda r: _ROLE_PRIORITY[r.role])
        return registrations[0].provider

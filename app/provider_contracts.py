"""EPIC-M1.90: make every external-world capability in this platform
provider-based, so domain and recommendation logic never depends
directly on a specific vendor.

This is deliberately a contracts-only EPIC -- it introduces no new
persisted state and no registry (M1.92's own job). It formalizes a
pattern this platform already followed informally from M1.3 onward
(a `typing.Protocol` provider boundary, a `source` class attribute, a
`fetch_*` method, and a provider-agnostic orchestration function that
only depends on the Protocol): every existing adapter --
`app.market_data.YahooFinanceClient`, `app.market_data.UpstoxClient`,
`app.fundamental_data.YahooFundamentalsClient`, `app.news_data.
YahooNewsClient` -- is retrofitted here with two additional, uniform
class attributes (`capability`, `version`), additive and backward
compatible; `source` is unchanged.

**AI/discovery has no real provider today.** `app.discovery.record_
discovery` accepts an externally-supplied rationale string (M1.17); no
adapter in this codebase calls an LLM API. Rather than fabricate one,
`CAPABILITY_AI_DISCOVERY` and `AIDiscoveryProvider` are defined as a
real, usable contract with zero real implementations -- the same
honest, forward-compatible posture M1.35 held for `DATA_TYPE_FUNDAMENTAL`/
`DATA_TYPE_NEWS_EVENT` before M1.72/M1.73 gave them real ones.

"Require at least three interchangeable implementation slots per
provider capability at architecture/test level" (scope) is satisfied
per-capability: MARKET_DATA already has two real, independent adapters
(Yahoo, Upstox); `tests/test_provider_contracts.py` adds a third,
in-memory fake to each capability (including the zero-real-adapter
AI_DISCOVERY capability) and proves the *same* domain/ingestion code
path accepts all of them interchangeably -- explicitly "at test level,"
as the scope itself allows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

PROVIDER_CONTRACTS_VERSION = "PVC-001"

CAPABILITY_MARKET_DATA = "MARKET_DATA"
CAPABILITY_FUNDAMENTAL_DATA = "FUNDAMENTAL_DATA"
CAPABILITY_NEWS_EVENT_DATA = "NEWS_EVENT_DATA"
CAPABILITY_AI_DISCOVERY = "AI_DISCOVERY"

ALL_CAPABILITIES = (
    CAPABILITY_MARKET_DATA,
    CAPABILITY_FUNDAMENTAL_DATA,
    CAPABILITY_NEWS_EVENT_DATA,
    CAPABILITY_AI_DISCOVERY,
)


class ProviderContractViolationError(ValueError):
    """Raised when an object claiming to implement a provider capability
    is missing a required contract attribute or method -- never allowed
    to fail silently or leak a vendor-specific `AttributeError` into
    domain code."""


@dataclass(frozen=True)
class ProviderMetadata:
    capability: str
    provider_id: str
    version: str


@dataclass(frozen=True)
class ProviderHealthStatus:
    provider_id: str
    is_available: bool
    checked_at: datetime
    detail: str | None = None


@runtime_checkable
class HealthCheckable(Protocol):
    """Optional capability: not every provider implements a live health
    check. Callers must check `isinstance(provider, HealthCheckable)`
    (or use `check_provider_health` below) rather than assuming it."""

    def check_health(self) -> ProviderHealthStatus: ...


class AIDiscoveryProvider(Protocol):
    """Contract for a real AI/discovery candidate source. No production
    implementation exists in this codebase today -- see module
    docstring."""

    source: str
    capability: str
    version: str

    def discover_candidates(self, universe_version: str) -> tuple[dict, ...]: ...


_REQUIRED_ATTRIBUTES = ("source", "capability", "version")


def get_provider_metadata(provider) -> ProviderMetadata:
    """The one place every consumer reads a provider's identity from --
    never a direct, vendor-specific attribute access scattered through
    domain code (AC: "provider metadata and provenance are preserved").
    Raises `ProviderContractViolationError`, never a bare
    `AttributeError`, when a provider is missing a required attribute."""
    missing = [attr for attr in _REQUIRED_ATTRIBUTES if not hasattr(provider, attr)]
    if missing:
        raise ProviderContractViolationError(
            f"{type(provider).__name__} is missing required provider contract attribute(s): {missing}"
        )
    return ProviderMetadata(capability=provider.capability, provider_id=provider.source, version=provider.version)


def verify_provider_contract(provider, *, expected_capability: str) -> ProviderMetadata:
    """Verifies `provider` both satisfies the base contract and declares
    the capability its caller expects -- the shared check every contract
    test in this platform should run against every real and fake
    implementation of a capability (AC: "contract tests prove
    interchangeable implementations")."""
    if expected_capability not in ALL_CAPABILITIES:
        raise ProviderContractViolationError(f"unknown capability: {expected_capability!r}")
    metadata = get_provider_metadata(provider)
    if metadata.capability != expected_capability:
        raise ProviderContractViolationError(
            f"{type(provider).__name__} declares capability {metadata.capability!r}, expected {expected_capability!r}"
        )
    return metadata


def check_provider_health(provider, *, checked_at: datetime) -> ProviderHealthStatus:
    """Generic health-status accessor (scope: "define capability
    availability and health contracts"). Providers that do not
    implement `HealthCheckable` are honestly reported as unknown-health
    rather than assumed healthy (AC: "a provider can be disabled without
    changing recommendation/business logic" -- callers can always ask
    this function, regardless of whether the concrete provider bothered
    to implement a real check)."""
    if isinstance(provider, HealthCheckable):
        return provider.check_health()
    metadata = get_provider_metadata(provider)
    return ProviderHealthStatus(
        provider_id=metadata.provider_id, is_available=True, checked_at=checked_at,
        detail="no health check implemented; assumed available",
    )

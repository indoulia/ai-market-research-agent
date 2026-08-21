"""EPIC-M1.94: select the best available provider for a capability using
configured policy (M1.92's role priority) plus measured quality (M1.93's
per-provider success-rate verdicts), with safe, auditable fail-over.

Composes rather than duplicates: never reimplements M1.92's role-priority
ordering or M1.90's contract verification -- `ProviderRegistry.
get_registrations` is the only source of *which* providers exist and in
what order the platform's configuration prefers them; `ProviderQuality
Report.by_provider` (M1.93) is the only source of *how well* each one has
actually performed. This module's only new logic is deciding, given
both, which enabled-and-not-degraded provider to hand back, and recording
*why* every skipped candidate was skipped (scope: "provider failures are
visible and auditable").

Deliberately persists no selection decision anywhere: the decision is
fully reproducible from the registry's current configuration plus the
quality report's own already-persisted evidence (M1.93's AC: "provider
comparisons are reproducible") -- recomputing it *is* the audit trail, so
a parallel persisted log that could drift from what selection actually
used would add risk, not honesty.

Only a confirmed-poor verdict (`VERDICT_WEAK`) counts as "degraded" and
is temporarily suppressed (scope: "detect provider degradation and
temporarily suppress unhealthy providers"). `VERDICT_INSUFFICIENT_SAMPLE`
-- a provider with too little history to judge, not a provider with a
proven bad track record -- is never treated as degraded; suppressing an
unproven provider would punish newness, not unreliability, and would make
it impossible for a newly-registered provider to ever accumulate the
sample it needs. The suppression is temporary in the truest sense: it is
recomputed fresh from the latest quality report on every call, never
written back into the registry's own `enabled` flag (M1.92's own,
separate, manually-controlled mechanism) -- a provider whose measured
success rate recovers is selectable again on the very next call with no
configuration change at all.

"Preserve actual provider identity in every external-world result" and
"prevent provider switching from changing historical records" (scope/AC)
hold structurally, unchanged from M1.92: this module only ever returns
*which* already-configured provider instance to call next; it does not
touch, and has no path to touch, any already-persisted record's `source`/
`provider_id` column.
"""
from __future__ import annotations

from dataclasses import dataclass

from .discovery_effectiveness import VERDICT_WEAK
from .provider_contracts import CAPABILITY_FUNDAMENTAL_DATA, CAPABILITY_MARKET_DATA, CAPABILITY_NEWS_EVENT_DATA
from .provider_quality import ProviderQualityReport
from .provider_registry import NoProviderAvailableError, ProviderRegistry, ROLE_OPTIONAL, ROLE_PRIMARY, ROLE_SECONDARY
from .refresh_policy import DATA_TYPE_FUNDAMENTAL, DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT

PROVIDER_SELECTION_VERSION = "PVS-001"

_ROLE_PRIORITY = {ROLE_PRIMARY: 0, ROLE_SECONDARY: 1, ROLE_OPTIONAL: 2}

# M1.35's DataFetchAttempt.data_type vocabulary and M1.90's capability
# vocabulary happen to share the same string for MARKET_DATA and
# FUNDAMENTAL_DATA but NOT for news ("NEWS_EVENT" vs "NEWS_EVENT_DATA") --
# a real, pre-existing mismatch this module must bridge explicitly rather
# than assume string equality. CAPABILITY_AI_DISCOVERY has no data_type
# analog at all: M1.35 never defined a freshness policy for it, since
# discovery attempts are never recorded via record_fetch_attempt -- so an
# AI-discovery provider is never suppressed as "degraded" here (honest:
# there is no fetch-attempt-based signal to judge it by; M1.65's
# discovery-effectiveness report, composed into M1.93's own report, is
# the real quality signal for that capability).
_CAPABILITY_TO_DATA_TYPE = {
    CAPABILITY_MARKET_DATA: DATA_TYPE_MARKET,
    CAPABILITY_FUNDAMENTAL_DATA: DATA_TYPE_FUNDAMENTAL,
    CAPABILITY_NEWS_EVENT_DATA: DATA_TYPE_NEWS_EVENT,
}

SKIP_REASON_DISABLED = "disabled"
SKIP_REASON_DEGRADED = "degraded"


@dataclass(frozen=True)
class SkippedProvider:
    provider_id: str
    role: str
    reason: str


@dataclass(frozen=True)
class ProviderSelectionDecision:
    version: str
    capability: str
    selected_provider_id: str | None
    selected_role: str | None
    skipped: tuple[SkippedProvider, ...]


class NoHealthyProviderAvailableError(NoProviderAvailableError):
    """Raised when every registered provider for a capability is either
    disabled or degraded -- an honest failure (AC: "failed providers can
    fail over safely" means failing loudly once every option is
    exhausted, never silently returning a provider known to be
    unreliable). Carries the full `decision` so the caller can log or
    surface exactly which providers were skipped and why (scope:
    "provider failures are visible and auditable")."""

    def __init__(self, decision: ProviderSelectionDecision) -> None:
        self.decision = decision
        skipped_summary = [(s.provider_id, s.reason) for s in decision.skipped]
        super().__init__(
            f"no enabled, non-degraded provider available for capability {decision.capability!r}; "
            f"skipped: {skipped_summary}"
        )


def _quality_verdict(quality_report: ProviderQualityReport, *, capability: str, provider_id: str) -> str | None:
    data_type = _CAPABILITY_TO_DATA_TYPE.get(capability)
    if data_type is None:
        return None
    for metric in quality_report.by_provider:
        if metric.data_type == data_type and metric.provider_id == provider_id:
            return metric.verdict
    return None


def select_provider(
    registry: ProviderRegistry,
    quality_report: ProviderQualityReport,
    capability: str,
) -> tuple[object, ProviderSelectionDecision]:
    """Returns `(provider, decision)` for the highest-priority enabled,
    non-degraded provider registered for `capability` -- role priority
    first (scope: "capability-specific provider routing", "primary/
    secondary/fallback provider policies"), then measured quality (scope:
    "route based on quality ... and availability"). Raises
    `NoHealthyProviderAvailableError` -- carrying the decision recording
    every skip and its reason -- when nothing usable remains, rather than
    silently returning a disabled or proven-unreliable provider."""
    registrations = sorted(registry.get_registrations(capability), key=lambda r: _ROLE_PRIORITY[r.role])

    skipped: list[SkippedProvider] = []
    for registration in registrations:
        if not registration.enabled:
            skipped.append(SkippedProvider(provider_id=registration.provider_id, role=registration.role, reason=SKIP_REASON_DISABLED))
            continue

        verdict = _quality_verdict(quality_report, capability=capability, provider_id=registration.provider_id)
        if verdict == VERDICT_WEAK:
            skipped.append(SkippedProvider(provider_id=registration.provider_id, role=registration.role, reason=SKIP_REASON_DEGRADED))
            continue

        decision = ProviderSelectionDecision(
            version=PROVIDER_SELECTION_VERSION,
            capability=capability,
            selected_provider_id=registration.provider_id,
            selected_role=registration.role,
            skipped=tuple(skipped),
        )
        return registration.provider, decision

    decision = ProviderSelectionDecision(
        version=PROVIDER_SELECTION_VERSION,
        capability=capability,
        selected_provider_id=None,
        selected_role=None,
        skipped=tuple(skipped),
    )
    raise NoHealthyProviderAvailableError(decision)

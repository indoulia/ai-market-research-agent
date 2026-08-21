"""EPIC-M1.93: measure provider quality, cost, latency, availability and
failure behavior per CONCRETE PROVIDER, not just per capability/data type
(M1.64's `data_source_reliability` already does the latter), so provider
decisions can be evidence-based instead of relying on a fixed vendor
preference.

Composes rather than duplicates M1.64: same `VERDICT_OK`/`VERDICT_WEAK`/
`VERDICT_INSUFFICIENT_SAMPLE` vocabulary, same `RELIABILITY_SUCCESS_
THRESHOLD` and `MIN_SAMPLE_SIZE_FOR_COMPARISON` thresholds -- this module
segments the exact same `DataFetchAttempt` log M1.64 already reads, one
level finer: by `(data_type, provider_id)` instead of just `data_type`.
`provider_id` is this EPIC's own additive column on `DataFetchAttempt`
(nullable, migration 0067); rows recorded before this EPIC -- or by any
caller that never supplied one -- have `provider_id IS NULL` and are
honestly excluded from provider-level comparison rather than guessed at
("poor provider quality can be detected without silently changing
historical evidence": those old rows are never touched or reinterpreted).

"Track provider cost/usage metrics" (scope) is answered honestly: every
provider adapter implemented in this codebase today (Yahoo, Upstox,
Stooq, Alpha Vantage, Finnhub, Ollama) is free, so
`PROVIDER_COST_PER_REQUEST_USD` reports zero for every one of them -- the
field and the multiplication are real and ready for a future paid
provider, never a fabricated nonzero number.

"Measure rate-limit and availability behavior" (scope) composes M1.90's
`check_provider_health` directly against whatever live provider instances
a caller supplies (e.g. from M1.92's registry) -- this module implements
no new health-check mechanism of its own.

Read-only and deterministic; writes nothing anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .data_source_reliability import RELIABILITY_SUCCESS_THRESHOLD
from .discovery_effectiveness import (
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OK,
    VERDICT_WEAK,
    DiscoveryEffectivenessReport,
    compute_discovery_effectiveness_report,
)
from .models import DataFetchAttempt
from .provider_contracts import ProviderHealthStatus, check_provider_health
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

PROVIDER_QUALITY_VERSION = "PVQ-001"

# Every concrete provider adapter implemented in this codebase today is
# free to call. A future paid provider would record its real per-request
# cost here -- this module never guesses or fabricates a nonzero cost for
# a provider that isn't in this table.
PROVIDER_COST_PER_REQUEST_USD: dict[str, Decimal] = {
    "yahoo-finance": Decimal("0"),
    "upstox-v3": Decimal("0"),
    "stooq": Decimal("0"),
    "alpha-vantage": Decimal("0"),
    "finnhub": Decimal("0"),
    "ollama": Decimal("0"),
}


@dataclass(frozen=True)
class ProviderQualityMetric:
    data_type: str
    provider_id: str
    total_attempts: int
    successful_attempts: int
    failed_attempts: int
    success_rate: Decimal | None
    estimated_cost_usd: Decimal | None
    verdict: str


@dataclass(frozen=True)
class ProviderQualityReport:
    version: str
    computed_at: datetime
    by_provider: tuple[ProviderQualityMetric, ...]
    health_statuses: tuple[ProviderHealthStatus, ...]
    ai_discovery_effectiveness: DiscoveryEffectivenessReport


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _verdict(sample_count: int, success_rate: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or success_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if success_rate < RELIABILITY_SUCCESS_THRESHOLD:
        return VERDICT_WEAK
    return VERDICT_OK


def _provider_metrics(session: Session) -> tuple[ProviderQualityMetric, ...]:
    rows = session.execute(
        select(DataFetchAttempt.data_type, DataFetchAttempt.provider_id, DataFetchAttempt.success)
        .where(DataFetchAttempt.provider_id.is_not(None))
    ).all()

    buckets: dict[tuple[str, str], dict[str, int]] = {}
    for data_type, provider_id, success in rows:
        bucket = buckets.setdefault((data_type, provider_id), {"total": 0, "success": 0})
        bucket["total"] += 1
        if success:
            bucket["success"] += 1

    metrics = []
    for data_type, provider_id in sorted(buckets):
        bucket = buckets[(data_type, provider_id)]
        total = bucket["total"]
        successful = bucket["success"]
        success_rate = _rate(successful, total)
        cost_per_request = PROVIDER_COST_PER_REQUEST_USD.get(provider_id)
        estimated_cost = cost_per_request * total if cost_per_request is not None else None
        metrics.append(
            ProviderQualityMetric(
                data_type=data_type,
                provider_id=provider_id,
                total_attempts=total,
                successful_attempts=successful,
                failed_attempts=total - successful,
                success_rate=success_rate,
                estimated_cost_usd=estimated_cost,
                verdict=_verdict(total, success_rate),
            )
        )
    return tuple(metrics)


def compute_provider_quality_report(
    session: Session, *, computed_at: datetime, providers: tuple[object, ...] = (),
) -> ProviderQualityReport:
    """Deterministic aggregate over M1.35's `DataFetchAttempt` log,
    segmented by `(data_type, provider_id)` -- the genuinely new
    granularity M1.64's own per-data-type report does not have (scope:
    "compare providers by capability"). `providers`, if supplied, are
    live provider instances (e.g. resolved via M1.92's registry) to run
    M1.90's `check_provider_health` against; optional, since not every
    caller has live instances on hand when it only wants historical
    metrics (AC: "reliability and latency are measurable", "provider
    comparisons are reproducible" -- calling this twice with the same
    session state always returns equal reports).

    "Measure AI/provider output quality against validated outcomes where
    applicable" (scope) is satisfied by composing M1.65's own
    `compute_discovery_effectiveness_report` rather than duplicating it:
    a discovery `source` (e.g. `SOURCE_CHATGPT`) already *is* an
    AI/discovery provider identity, and M1.65 already measures its
    candidates' real win/loss outcomes end-to-end -- there is nothing
    honest to add here beyond exposing that existing report alongside
    fetch-provider quality."""
    health_statuses = tuple(check_provider_health(provider, checked_at=computed_at) for provider in providers)
    return ProviderQualityReport(
        version=PROVIDER_QUALITY_VERSION,
        computed_at=computed_at,
        by_provider=_provider_metrics(session),
        health_statuses=health_statuses,
        ai_discovery_effectiveness=compute_discovery_effectiveness_report(session),
    )

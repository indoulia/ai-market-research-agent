"""EPIC-M1.16: expose the historical truth of recommendation performance,
building on M1.6's deterministic performance aggregates over M1.5-evaluated
outcomes, by additionally flagging which 1/3/5/7-day horizons and which
predicted-probability buckets are performing weakly relative to the overall
success rate -- but only when each one has enough samples to support the
comparison. Never hides a failure or an unevaluable recommendation to make the
report look better: an under-sampled horizon/bucket is reported as an explicit
INSUFFICIENT_SAMPLE verdict, never silently omitted and never falsely called OK.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from .performance import (
    HorizonPerformance,
    PerformanceReport,
    ProbabilityBucketPerformance,
    compute_performance_report,
)

TRUST_REPORT_VERSION = "TRUST-001"

# Fixed product/policy constants, bumped via TRUST_REPORT_VERSION whenever changed.
MIN_SAMPLE_SIZE_FOR_COMPARISON = 20
WEAKNESS_MARGIN = Decimal("0.10")

VERDICT_OK = "OK"
VERDICT_WEAK = "WEAK"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


@dataclass(frozen=True)
class HorizonTrust:
    horizon: HorizonPerformance
    verdict: str


@dataclass(frozen=True)
class ProbabilityBucketTrust:
    bucket: ProbabilityBucketPerformance
    verdict: str


@dataclass(frozen=True)
class TrustReport:
    report_version: str
    performance: PerformanceReport
    horizon_trust: tuple[HorizonTrust, ...]
    probability_bucket_trust: tuple[ProbabilityBucketTrust, ...]


def _verdict(sample_count: int, success_rate: Decimal | None, overall_success_rate: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or success_rate is None or overall_success_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if overall_success_rate - success_rate >= WEAKNESS_MARGIN:
        return VERDICT_WEAK
    return VERDICT_OK


def compute_trust_report(session: Session) -> TrustReport:
    """Every verdict is derived only from M1.6's already-deterministic aggregates
    (no LLM reasoning, no separate query) so the trust report stays reproducible
    from the same persisted Prediction/PredictionOutcome rows M1.6 already uses."""
    performance = compute_performance_report(session)

    horizon_trust = tuple(
        HorizonTrust(
            horizon=horizon,
            verdict=_verdict(horizon.evaluated_count, horizon.success_rate, performance.overall_success_rate),
        )
        for horizon in performance.by_horizon
    )
    bucket_trust = tuple(
        ProbabilityBucketTrust(
            bucket=bucket,
            verdict=_verdict(bucket.evaluated_count, bucket.success_rate, performance.overall_success_rate),
        )
        for bucket in performance.by_probability_bucket
    )

    return TrustReport(
        report_version=TRUST_REPORT_VERSION,
        performance=performance,
        horizon_trust=horizon_trust,
        probability_bucket_trust=bucket_trust,
    )

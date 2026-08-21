"""EPIC-M1.116: optimize MRA's provider/model usage so prediction
quality improves without unnecessary external cost or latency, while
never letting a cost-driven choice silently fall below the minimum
quality policy this platform already established (M1.64's
`RELIABILITY_SUCCESS_THRESHOLD`, reused unchanged as the quality floor
via M1.93's own `VERDICT_WEAK`/`VERDICT_OK` classification).

**Measure provider/model marginal predictive value / compare quality,
latency and cost trade-offs:** `compute_cost_quality_tradeoff` composes
M1.93's already-computed `ProviderQualityReport` (per-provider success
rate and verdict) with M1.93's own `PROVIDER_COST_PER_REQUEST_USD` --
never recomputing either. Every real provider adapter in this platform
today is free (`Decimal("0")`); this module reports that honestly
rather than fabricating a nonzero cost, and the framework is real and
ready the moment a future paid provider is added.

**Route expensive analysis only where it improves validated outcomes /
use cheaper/local providers for suitable tasks:** among providers whose
verdict is not `VERDICT_WEAK` (a proven-poor track record -- the same
"insufficient sample is not the same as unreliable" posture M1.94's own
selection logic already established), the free provider with the best
measured quality is preferred by default (`COST_OPTIMIZED_SELECTION`).
A paid provider is only ever recommended when no quality-acceptable free
provider exists (`QUALITY_JUSTIFIES_COST`) -- spending only where the
free alternative genuinely doesn't clear the quality bar.

**Ensure cost optimization never silently reduces minimum prediction-
quality policy:** a `VERDICT_WEAK` provider is *never* recommended
regardless of cost; if every candidate for a data type is `VERDICT_WEAK`,
the report honestly returns `NO_ACCEPTABLE_PROVIDER` with no recommendation
at all, rather than falling back to a free-but-proven-poor option.

**Cache reusable evidence safely with freshness controls:** already
covered structurally by M1.35's refresh-policy freshness checks (data
already fresh enough is never re-fetched) -- this module adds no new
caching mechanism of its own; there is no cache infrastructure elsewhere
in this codebase to safely extend within this EPIC's scope.

Read-only: no write path to `ProviderRegistry`, `ProviderQualityReport`,
or any provider-selection table -- this is a propose-only recommendation
for a future deployment/configuration step, the same posture this whole
family of EPICs already established.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .data_source_reliability import RELIABILITY_SUCCESS_THRESHOLD
from .discovery_effectiveness import VERDICT_WEAK
from .models import CostQualityTradeoffReport
from .provider_quality import PROVIDER_COST_PER_REQUEST_USD, ProviderQualityReport

COST_QUALITY_VERSION = "CQO-001"

VERDICT_COST_OPTIMIZED_SELECTION = "COST_OPTIMIZED_SELECTION"
VERDICT_QUALITY_JUSTIFIES_COST = "QUALITY_JUSTIFIES_COST"
VERDICT_NO_ACCEPTABLE_PROVIDER = "NO_ACCEPTABLE_PROVIDER"


def compute_cost_quality_tradeoff(
    session: Session, *, data_type: str, quality_report: ProviderQualityReport, computed_at: datetime
) -> CostQualityTradeoffReport:
    """Always computes and persists a fresh, independent report row --
    the same "report" posture as M1.85/M1.99/M1.102/M1.108/M1.109/M1.111.
    Never recomputes M1.93's own quality metrics or cost table."""
    metrics = [m for m in quality_report.by_provider if m.data_type == data_type]

    candidates = []
    for metric in metrics:
        cost = PROVIDER_COST_PER_REQUEST_USD.get(metric.provider_id)
        candidates.append({
            "provider_id": metric.provider_id,
            "success_rate": str(metric.success_rate) if metric.success_rate is not None else None,
            "verdict": metric.verdict,
            "cost_per_request_usd": str(cost) if cost is not None else None,
            "is_free": (cost == Decimal("0")) if cost is not None else False,
        })

    acceptable = [m for m in metrics if m.verdict != VERDICT_WEAK]
    # A provider with no known cost (not yet in PROVIDER_COST_PER_REQUEST_USD)
    # is neither assumed free nor assumed paid -- it is simply excluded from
    # a cost-based recommendation until its real cost is known.
    free_acceptable = [m for m in acceptable if PROVIDER_COST_PER_REQUEST_USD.get(m.provider_id) == Decimal("0")]
    paid_acceptable = [
        m for m in acceptable
        if PROVIDER_COST_PER_REQUEST_USD.get(m.provider_id) is not None and PROVIDER_COST_PER_REQUEST_USD[m.provider_id] > Decimal("0")
    ]

    def _best(pool):
        return max(pool, key=lambda m: (m.success_rate if m.success_rate is not None else Decimal("-1"), m.provider_id))

    best_free = _best(free_acceptable) if free_acceptable else None
    best_paid = _best(paid_acceptable) if paid_acceptable else None

    if best_free is not None:
        recommended = best_free
        verdict = VERDICT_COST_OPTIMIZED_SELECTION
    elif best_paid is not None:
        recommended = best_paid
        verdict = VERDICT_QUALITY_JUSTIFIES_COST
    else:
        recommended = None
        verdict = VERDICT_NO_ACCEPTABLE_PROVIDER

    report = CostQualityTradeoffReport(
        data_type=data_type, provider_candidates=candidates,
        recommended_provider_id=(recommended.provider_id if recommended is not None else None),
        best_free_provider_id=(best_free.provider_id if best_free is not None else None),
        quality_floor=RELIABILITY_SUCCESS_THRESHOLD, verdict=verdict, computed_at=computed_at,
        report_rule_version=COST_QUALITY_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_cost_quality_history(session: Session, data_type: str) -> tuple[CostQualityTradeoffReport, ...]:
    return tuple(
        session.scalars(
            select(CostQualityTradeoffReport).where(CostQualityTradeoffReport.data_type == data_type).order_by(CostQualityTradeoffReport.id.asc())
        ).all()
    )

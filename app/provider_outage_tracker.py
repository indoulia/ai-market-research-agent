"""EPIC-M1.114: prevent provider outages, rate limits or degraded
responses from silently producing stale or unreliable predictions, by
preserving -- over time -- whether a data type's registered providers
were experiencing no, partial, or total degradation.

**Detect provider health degradation / fail over through M1.94 provider
routing / recover automatically when providers return to healthy
state:** all three already hold, unchanged, via M1.94's own
`select_provider` -- it already recomputes fresh from M1.93's quality
report on every call, treats only a confirmed `VERDICT_WEAK` as
degraded (never an unproven `VERDICT_INSUFFICIENT_SAMPLE`), and
recovers automatically the moment measured quality improves, with no
configuration change. This module does not duplicate that selection
logic; it only adds the ONE thing M1.94 deliberately never does --
persist a historical record of degradation over time -- because M1.94's
own docstring explains that a persisted *selection* log would risk
drifting from what selection actually used, which is a different
concern from preserving *outage continuity history* for later review.

**Track partial data availability explicitly:** `record_outage_snapshot`
classifies a data type's severity as `NONE` (no registered provider
degraded), `PARTIAL` (some but not all), or `TOTAL` (every registered
provider degraded) -- reusing M1.93's own `ProviderQualityMetric.verdict`
unchanged, never recomputing provider quality itself.

**Preserve outage/fallback provenance:** every snapshot names exactly
which provider ids were degraded (`degraded_provider_ids`), immutably.

**Prevent stale provider data from being treated as current / suppress
affected predictions when minimum evidence policy is not satisfied:**
already covered by M1.35's freshness checks, M1.74's evidence-quality
gate, and M1.112's assumption-decay tracker -- not duplicated here.
This module's own signal is a read-only input a future revision of
those could compose; it has no write path to `Prediction` or any
recommendation-facing table.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .discovery_effectiveness import VERDICT_WEAK
from .models import ProviderOutageSnapshot
from .provider_quality import ProviderQualityReport

OUTAGE_SNAPSHOT_VERSION = "POT-001"

SEVERITY_NONE = "NONE"
SEVERITY_PARTIAL = "PARTIAL"
SEVERITY_TOTAL = "TOTAL"


def record_outage_snapshot(
    session: Session,
    *,
    data_type: str,
    registered_provider_ids: tuple[str, ...],
    quality_report: ProviderQualityReport,
    evaluated_at: datetime,
) -> ProviderOutageSnapshot:
    """Idempotent by `(data_type, evaluated_at)`. A registered provider
    with no measured quality yet (M1.93 `VERDICT_INSUFFICIENT_SAMPLE`,
    or simply no metric at all) is counted as healthy, not degraded --
    the same "insufficient sample is not the same as unreliable" posture
    M1.94's own selection logic already established; only a confirmed
    `VERDICT_WEAK` counts against a provider here."""
    existing = session.scalar(
        select(ProviderOutageSnapshot).where(
            ProviderOutageSnapshot.data_type == data_type, ProviderOutageSnapshot.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    metrics_by_provider = {m.provider_id: m for m in quality_report.by_provider if m.data_type == data_type}
    degraded_provider_ids = sorted(
        provider_id for provider_id in registered_provider_ids
        if metrics_by_provider.get(provider_id) is not None and metrics_by_provider[provider_id].verdict == VERDICT_WEAK
    )

    total = len(registered_provider_ids)
    degraded = len(degraded_provider_ids)
    healthy = total - degraded

    if degraded == 0:
        severity = SEVERITY_NONE
    elif degraded >= total:
        severity = SEVERITY_TOTAL
    else:
        severity = SEVERITY_PARTIAL

    snapshot = ProviderOutageSnapshot(
        data_type=data_type, total_registered_providers=total, healthy_provider_count=healthy,
        degraded_provider_count=degraded, degraded_provider_ids=degraded_provider_ids, severity=severity,
        evaluated_at=evaluated_at, snapshot_rule_version=OUTAGE_SNAPSHOT_VERSION,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_outage_history(session: Session, data_type: str) -> tuple[ProviderOutageSnapshot, ...]:
    return tuple(
        session.scalars(
            select(ProviderOutageSnapshot).where(ProviderOutageSnapshot.data_type == data_type).order_by(ProviderOutageSnapshot.id.asc())
        ).all()
    )


def get_latest_outage_snapshot(session: Session, data_type: str) -> ProviderOutageSnapshot | None:
    history = get_outage_history(session, data_type)
    return history[-1] if history else None

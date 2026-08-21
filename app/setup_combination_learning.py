"""EPIC-M1.108: discover which combinations of technical-bucket,
regime and horizon signals -- a "setup signature" -- consistently
produce useful positive outcomes, rather than only looking at one
dimension at a time (M1.85's own scope, deliberately not duplicated).

**Reproducible setup signatures** (scope) reuse M1.85's own SMA20-
distance/volume-ratio bucket vocabulary and M1.26's own regime
vocabulary directly off the already-immutable `PredictionAttribution
Snapshot` -- `setup_signature = f"{sma20_distance_bucket}_
{volume_ratio_bucket}"`, joined with `horizon_days` and `regime`, is a
deterministic function of already-captured, already-bucketed columns;
no new bucketing logic is introduced here.

**Control feature/combination explosion and multiple testing** (scope):
testing every distinct `(setup_signature, horizon_days, regime)`
combination at once is exactly the multiplicity problem M1.100 named
for experiment arms -- this module applies the same fixed, documented
Bonferroni-style scaling (`adjusted_margin = WEAKNESS_MARGIN *
multiplicity_trial_count`), but with `multiplicity_trial_count` counting
the number of *combinations* that clear the sample floor this run, not
M1.100's experiment-arm count (a genuinely different multiplicity
question, so M1.100's own function is not reused directly -- only the
underlying constant and scaling idea).

Reuses M1.85's exact `ASSOCIATION_SUCCESS`/`ASSOCIATION_FAILURE`/
`ASSOCIATION_NONE`/`ASSOCIATION_INSUFFICIENT_SAMPLE` vocabulary rather
than inventing a parallel one, and M1.85's own "always compute and
persist a fresh, independent report" posture (no idempotency check) --
the same pattern already used by `FactorAssociationReport`, M1.99's
`RankingEffectivenessReport`, and M1.102's
`TransitionPeriodPerformanceReport`.

Propose-only: no write path to any experiment, ranking, or Trust Score
table -- "feed validated setup evidence into experiments, ranking and
Trust Score" (scope) remains a future revision's job.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PredictionAttributionSnapshot, SetupCombinationReport
from .prediction_attribution import ASSOCIATION_FAILURE, ASSOCIATION_INSUFFICIENT_SAMPLE, ASSOCIATION_NONE, ASSOCIATION_SUCCESS
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

SETUP_COMBINATION_VERSION = "SCL-001"

REPORT_VERDICT_MEASURED = "MEASURED"
REPORT_VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _setup_signature(snapshot: PredictionAttributionSnapshot) -> str:
    return f"{snapshot.sma20_distance_bucket}_{snapshot.volume_ratio_bucket}"


def compute_setup_combination_report(session: Session, *, model_version: str, computed_at: datetime) -> SetupCombinationReport:
    """Always computes and persists a fresh, independent report row --
    never mutates a prior report, and never declares an association from
    a combination below `MIN_SAMPLE_SIZE_FOR_COMPARISON`."""
    snapshots = list(
        session.scalars(select(PredictionAttributionSnapshot).where(PredictionAttributionSnapshot.model_version == model_version)).all()
    )
    sample_count = len(snapshots)

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        report = SetupCombinationReport(
            model_version=model_version, sample_count=sample_count, combination_count_considered=0,
            multiplicity_trial_count=0, adjusted_margin=WEAKNESS_MARGIN, combinations=[],
            verdict=REPORT_VERDICT_INSUFFICIENT_SAMPLE, computed_at=computed_at, report_rule_version=SETUP_COMBINATION_VERSION,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    baseline_success_rate = _rate(sum(1 for s in snapshots if s.outcome == "SUCCESS"), sample_count)

    grouped: dict[tuple[str, int, str | None], list[str]] = {}
    for snapshot in snapshots:
        key = (_setup_signature(snapshot), snapshot.horizon_days, snapshot.regime)
        grouped.setdefault(key, []).append(snapshot.outcome)

    multiplicity_trial_count = max(1, sum(1 for outcomes in grouped.values() if len(outcomes) >= MIN_SAMPLE_SIZE_FOR_COMPARISON))
    adjusted_margin = WEAKNESS_MARGIN * Decimal(multiplicity_trial_count)

    combinations = []
    for setup_signature, horizon_days, regime in sorted(grouped, key=lambda k: (k[0], k[1], k[2] or "")):
        outcomes = grouped[(setup_signature, horizon_days, regime)]
        group_sample_count = len(outcomes)
        if group_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
            combinations.append({
                "setup_signature": setup_signature, "horizon_days": horizon_days, "regime": regime,
                "sample_count": group_sample_count, "success_rate": None, "association": ASSOCIATION_INSUFFICIENT_SAMPLE,
            })
            continue

        success_rate = _rate(sum(1 for o in outcomes if o == "SUCCESS"), group_sample_count)
        delta = success_rate - baseline_success_rate
        if delta >= adjusted_margin:
            association = ASSOCIATION_SUCCESS
        elif delta <= -adjusted_margin:
            association = ASSOCIATION_FAILURE
        else:
            association = ASSOCIATION_NONE
        combinations.append({
            "setup_signature": setup_signature, "horizon_days": horizon_days, "regime": regime,
            "sample_count": group_sample_count, "success_rate": str(success_rate), "association": association,
        })

    report = SetupCombinationReport(
        model_version=model_version, sample_count=sample_count, combination_count_considered=len(grouped),
        multiplicity_trial_count=multiplicity_trial_count, adjusted_margin=adjusted_margin, combinations=combinations,
        verdict=REPORT_VERDICT_MEASURED, computed_at=computed_at, report_rule_version=SETUP_COMBINATION_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_setup_combination_history(session: Session, model_version: str) -> tuple[SetupCombinationReport, ...]:
    return tuple(
        session.scalars(
            select(SetupCombinationReport).where(SetupCombinationReport.model_version == model_version).order_by(SetupCombinationReport.id.asc())
        ).all()
    )

"""EPIC-M1.66: make every recommendation decision -- qualified or rejected
-- reproducible from its exact inputs, evidence, rules, model, score,
target, SL, and confidence versions, consolidated into one immutable,
self-contained row.

Every field this module captures is already immutable somewhere else in
this platform (`Prediction` via M1.4/M1.13, `RecommendationGeneration` via
M1.8, `RecommendationPublication` via M1.47, `RecommendationEvidenceItem`
via M1.48) -- this module's own contribution is consolidation, not new
computation: denormalizing all of it into one row so a historical decision
can be reconstructed from a single query, without joining across five
tables or relying on their version constants still existing in code (AC:
"a historical recommendation can be reconstructed without current data").

Captures both qualified and rejected candidates (scope: "capture
qualification and rejection reasons") -- a rejected `RecommendationGeneration`
has no `Prediction` at all, so every `Prediction`/M1.47/M1.48-derived field
is `None` for it, and `rejection_reasons` carries M1.8's own
`failed_criteria` (AC: "every material decision has an explicit reason").
"""
from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence_snapshot import get_evidence_snapshot
from .models import DailyCandidateScan, Prediction, RecommendationDecisionTrace, RecommendationGeneration, ScanCandidate
from .recommendation_generator import OUTCOME_QUALIFIED
from .target_stop_loss import TARGET_STOP_METHODOLOGY_VERSION, get_publication

DECISION_TRACE_VERSION = "DTR-001"


def get_decision_trace(session: Session, recommendation_generation_id: int) -> RecommendationDecisionTrace | None:
    return session.scalar(
        select(RecommendationDecisionTrace).where(
            RecommendationDecisionTrace.recommendation_generation_id == recommendation_generation_id
        )
    )


def capture_decision_trace(
    session: Session, generation: RecommendationGeneration, *, traced_at: datetime
) -> RecommendationDecisionTrace:
    """Idempotent by `recommendation_generation_id` -- a decision, once
    traced, is never re-derived (AC: "trace data is immutable"), even if
    M1.47/M1.48 are run again later with different results. Consolidates
    whatever is available *at the time this is called*; a rejected
    candidate is traced immediately (no `Prediction` ever exists for it),
    while a qualified one should typically be traced after M1.47/M1.48 have
    run, so their outputs are captured too -- if they haven't run yet, this
    trace simply records `None` for those fields rather than fabricating
    them (the honest partial-coverage pattern used throughout this
    platform)."""
    existing = get_decision_trace(session, generation.id)
    if existing is not None:
        return existing

    scan_candidate = session.get(ScanCandidate, generation.scan_candidate_id)
    prediction = session.get(Prediction, generation.prediction_id) if generation.prediction_id is not None else None

    if prediction is not None:
        as_of_timestamp = prediction.as_of_timestamp
    else:
        scan = session.get(DailyCandidateScan, scan_candidate.scan_id)
        as_of_timestamp = datetime.combine(scan.scan_date, time.min, tzinfo=timezone.utc)

    target_price = stop_loss_price = target_stop_methodology_version = None
    evidence_snapshot: list = []
    if prediction is not None:
        publication = get_publication(session, prediction.id, methodology_version=TARGET_STOP_METHODOLOGY_VERSION)
        if publication is not None:
            target_price = publication.target_price
            stop_loss_price = publication.stop_loss_price
            target_stop_methodology_version = publication.methodology_version

        evidence_snapshot = [
            {
                "category": item.evidence_category,
                "status": item.status,
                "source": item.source,
                "reference": item.reference,
                "evidence_timestamp": item.evidence_timestamp.isoformat() if item.evidence_timestamp else None,
                "is_stale": item.is_stale,
            }
            for item in get_evidence_snapshot(session, prediction.id)
        ]

    trace = RecommendationDecisionTrace(
        recommendation_generation_id=generation.id,
        prediction_id=prediction.id if prediction is not None else None,
        stock_id=scan_candidate.stock_id,
        as_of_timestamp=as_of_timestamp,
        sma20_distance=scan_candidate.sma20_distance,
        volume_ratio_20d=scan_candidate.volume_ratio_20d,
        atr_percent=scan_candidate.atr_percent,
        entry_price=prediction.entry_price if prediction is not None else None,
        horizon_days=prediction.horizon_days if prediction is not None else None,
        target_return=prediction.target_return if prediction is not None else None,
        stop_return=prediction.stop_return if prediction is not None else None,
        predicted_probability=prediction.predicted_probability if prediction is not None else scan_candidate.predicted_probability,
        confidence=prediction.confidence if prediction is not None else scan_candidate.confidence,
        opportunity_score=prediction.opportunity_score if prediction is not None else None,
        model_version=prediction.model_version if prediction is not None else scan_candidate.model_version,
        feature_version=prediction.feature_version if prediction is not None else scan_candidate.feature_version,
        consensus_contract_version=generation.consensus_contract_version,
        horizon_selection_version=prediction.horizon_selection_version if prediction is not None else None,
        scoring_contract_version=prediction.scoring_contract_version if prediction is not None else None,
        target_stop_methodology_version=target_stop_methodology_version,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        qualification_outcome=generation.outcome,
        rejection_reasons=generation.failed_criteria if generation.outcome != OUTCOME_QUALIFIED else None,
        evidence_categories_snapshot=evidence_snapshot,
        traced_at=traced_at,
        decision_trace_version=DECISION_TRACE_VERSION,
    )
    session.add(trace)
    session.commit()
    session.refresh(trace)
    return trace

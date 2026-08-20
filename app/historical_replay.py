"""EPIC-M1.24: reconstruct a historical recommendation *decision* -- qualifying
or not -- using only the market data that existed as of the original scan
date, run through the platform's real, current consensus (M1.8) / scoring
(M1.9) / horizon (M1.10) functions, and compare the replayed decision against
what was actually persisted. This makes the effect of a later rule, model, or
data change on history directly measurable, and surfaces missing historical
input or a data-quality exclusion as an explicit limitation rather than a
fabricated result.

Anchored on `RecommendationGeneration` rather than `Prediction`, since a
generation exists for both qualifying and rejected candidates -- a rejected
one never got a `Prediction` row at all, but "would a rule/model change have
flipped this rejection" is exactly the kind of question this EPIC exists to
answer, so it must be replayable too.

Deliberately reuses `app.scan._evaluate_stock` (point-in-time feature
computation via the same pandas pipeline M1.12's real daily scan uses)
directly rather than duplicating ~50 lines of feature-computation logic in a
second implementation that could silently drift from the first. This module
never calls `session.add` on a `ScanCandidate`/`Prediction`/`RecommendationGeneration`
-- a replay is a dry-run computation compared against history, never a write
to production recommendation data (non-goal: "changing historical production
records").
"""
from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .consensus import ConsensusInputs, evaluate_positive_consensus
from .horizon import select_horizon
from .market_data.quality import NSE_TIMEZONE
from .models import DailyCandidateScan, MarketPrice, RecommendationGeneration, ReplayRun, ScanCandidate
from .recommendation_generator import OUTCOME_QUALIFIED
from .scan import SignalProvider, _evaluate_stock
from .scoring import ScoringInputs, compute_positive_opportunity_score

REPLAY_RULE_VERSION = "REPLAY-001"

LIMITATION_NO_HISTORICAL_DATA = "NO_HISTORICAL_MARKET_DATA"
LIMITATION_PREFIX_EXCLUDED_AT_REPLAY = "EXCLUDED_AT_REPLAY"


def replay_generation(
    session: Session,
    generation: RecommendationGeneration,
    signal_provider: SignalProvider,
    *,
    replayed_at: datetime,
) -> ReplayRun:
    """Replay one `RecommendationGeneration`'s decision. Deterministic and
    repeatable (scope item 7): given identical `MarketPrice` history up to the
    original scan date and the same `signal_provider`, this always recomputes
    the identical result. Leakage-safe by construction (scope items 1, 2, 6):
    the market-data query below is bounded by `MarketPrice.timestamp <=
    cutoff`, where `cutoff` is derived from the original scan's `scan_date` --
    no row timestamped after the original decision can ever be selected."""
    scan_candidate = session.get(ScanCandidate, generation.scan_candidate_id)
    scan = session.get(DailyCandidateScan, scan_candidate.scan_id)
    cutoff = datetime.combine(scan.scan_date, time.min, NSE_TIMEZONE)

    rows = list(
        session.scalars(
            select(MarketPrice)
            .where(MarketPrice.stock_id == scan_candidate.stock_id, MarketPrice.timestamp <= cutoff)
            .order_by(MarketPrice.timestamp.asc())
        ).all()
    )

    if not rows:
        return _persist(
            session,
            generation,
            replayed_at,
            limitation=LIMITATION_NO_HISTORICAL_DATA,
            replayed_qualifies=None,
            matches_original=None,
        )

    replayed_candidate = _evaluate_stock(
        scan_candidate.scan_id, scan_candidate.stock_id, rows, scan.scan_date, signal_provider
    )

    if not replayed_candidate.eligible:
        # Being excluded at replay time (missing/stale/invalid data as of the
        # original scan date) is itself a valid, explicit replay outcome --
        # not the same dimension as a consensus rejection, so it is not
        # compared as one; it can still be compared on "did a recommendation
        # exist," since exclusion also produced no Prediction.
        return _persist(
            session,
            generation,
            replayed_at,
            limitation=f"{LIMITATION_PREFIX_EXCLUDED_AT_REPLAY}:{replayed_candidate.exclusion_reason}",
            replayed_qualifies=None,
            matches_original=generation.prediction_id is None,
        )

    consensus = evaluate_positive_consensus(
        ConsensusInputs(
            predicted_probability=replayed_candidate.predicted_probability,
            confidence=replayed_candidate.confidence,
            sma20_distance=replayed_candidate.sma20_distance,
            volume_ratio_20d=replayed_candidate.volume_ratio_20d,
            data_quality_passed=replayed_candidate.data_quality_passed,
        )
    )

    if not consensus.qualifies:
        return _persist(
            session,
            generation,
            replayed_at,
            replayed_qualifies=False,
            replayed_failed_criteria=[c.name for c in consensus.failed_criteria()],
            replayed_predicted_probability=replayed_candidate.predicted_probability,
            replayed_model_version=replayed_candidate.model_version,
            replayed_feature_version=replayed_candidate.feature_version,
            replayed_consensus_contract_version=consensus.contract_version,
            matches_original=generation.outcome != OUTCOME_QUALIFIED,
        )

    score = compute_positive_opportunity_score(
        ScoringInputs(
            predicted_probability=replayed_candidate.predicted_probability,
            confidence=replayed_candidate.confidence,
            sma20_distance=replayed_candidate.sma20_distance,
            volume_ratio_20d=replayed_candidate.volume_ratio_20d,
        )
    )
    horizon = select_horizon(replayed_candidate.atr_percent)

    return _persist(
        session,
        generation,
        replayed_at,
        replayed_qualifies=True,
        replayed_opportunity_score=score.total_score,
        replayed_horizon_days=horizon.horizon_days,
        replayed_predicted_probability=replayed_candidate.predicted_probability,
        replayed_model_version=replayed_candidate.model_version,
        replayed_feature_version=replayed_candidate.feature_version,
        replayed_consensus_contract_version=consensus.contract_version,
        replayed_scoring_contract_version=score.contract_version,
        replayed_horizon_selection_version=horizon.selection_version,
        matches_original=generation.outcome == OUTCOME_QUALIFIED,
    )


def _persist(
    session: Session,
    generation: RecommendationGeneration,
    replayed_at: datetime,
    *,
    limitation: str | None = None,
    replayed_qualifies: bool | None = None,
    replayed_failed_criteria: list | None = None,
    replayed_opportunity_score: Decimal | None = None,
    replayed_horizon_days: int | None = None,
    replayed_predicted_probability: Decimal | None = None,
    replayed_model_version: str | None = None,
    replayed_feature_version: str | None = None,
    replayed_consensus_contract_version: str | None = None,
    replayed_scoring_contract_version: str | None = None,
    replayed_horizon_selection_version: str | None = None,
    matches_original: bool | None = None,
) -> ReplayRun:
    run = ReplayRun(
        recommendation_generation_id=generation.id,
        replayed_at=replayed_at,
        limitation=limitation,
        replayed_qualifies=replayed_qualifies,
        replayed_failed_criteria=replayed_failed_criteria,
        replayed_opportunity_score=replayed_opportunity_score,
        replayed_horizon_days=replayed_horizon_days,
        replayed_predicted_probability=replayed_predicted_probability,
        replayed_model_version=replayed_model_version,
        replayed_feature_version=replayed_feature_version,
        replayed_consensus_contract_version=replayed_consensus_contract_version,
        replayed_scoring_contract_version=replayed_scoring_contract_version,
        replayed_horizon_selection_version=replayed_horizon_selection_version,
        matches_original=matches_original,
        replay_rule_version=REPLAY_RULE_VERSION,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run

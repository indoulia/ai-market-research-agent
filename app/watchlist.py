"""EPIC-M1.7: let a user-provided watchlist stock be evaluated against exactly the
same positive-opportunity criteria used for market-wide discovered candidates --
app/consensus.py's M1.8 positive-consensus gate, the only such mechanism in the
repository (scope item 2: "the same positive-opportunity evaluation used for
discovered candidates"). A qualifying stock is promoted to a real recommendation
(M1.4); a non-qualifying one is placed in backlog with an explicit reason and its
failed criteria, never as a negative/sell recommendation.
"""
from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .consensus import ConsensusInputs, evaluate_positive_consensus, record_qualifying_recommendation
from .models import WatchlistEvaluation

BACKLOG_REASON = "NOT MATCHING POSITIVE CONSENSUS"

OUTCOME_PROMOTED = "PROMOTED"
OUTCOME_BACKLOG = "BACKLOG"

# Every field on a watchlist evaluation is a historical fact about that evaluation run;
# none of it should ever change after creation. Re-evaluation (scope item 6) always
# inserts a new row instead.
IMMUTABLE_FIELDS = (
    "stock_id",
    "evaluated_at",
    "consensus_contract_version",
    "qualifies",
    "failed_criteria",
    "outcome",
    "backlog_reason",
    "prediction_id",
)


class WatchlistEvaluationImmutableError(RuntimeError):
    pass


@event.listens_for(WatchlistEvaluation, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise WatchlistEvaluationImmutableError(
            f"watchlist evaluation {target.id} field(s) {changed} cannot be modified after creation"
        )


def evaluate_watchlist_candidate(
    session: Session,
    *,
    stock_id: int,
    evaluated_at: datetime,
    consensus_inputs: ConsensusInputs,
    recommendation_kwargs: dict,
) -> WatchlistEvaluation:
    """Evaluate one watchlist stock. Always inserts a brand-new
    `WatchlistEvaluation` row -- never updates or looks up a prior one -- so repeated
    calls (re-evaluation as new market data arrives) never overwrite earlier history."""
    evaluation = evaluate_positive_consensus(consensus_inputs)

    if evaluation.qualifies:
        prediction = record_qualifying_recommendation(
            session, evaluation, stock_id=stock_id, **recommendation_kwargs
        )
        record = WatchlistEvaluation(
            stock_id=stock_id,
            evaluated_at=evaluated_at,
            consensus_contract_version=evaluation.contract_version,
            qualifies=True,
            failed_criteria=[],
            outcome=OUTCOME_PROMOTED,
            backlog_reason=None,
            prediction_id=prediction.id,
        )
    else:
        record = WatchlistEvaluation(
            stock_id=stock_id,
            evaluated_at=evaluated_at,
            consensus_contract_version=evaluation.contract_version,
            qualifies=False,
            failed_criteria=[c.name for c in evaluation.failed_criteria()],
            outcome=OUTCOME_BACKLOG,
            backlog_reason=BACKLOG_REASON,
            prediction_id=None,
        )

    session.add(record)
    session.flush()
    return record


def get_watchlist_history(session: Session, stock_id: int) -> list[WatchlistEvaluation]:
    return list(
        session.scalars(
            select(WatchlistEvaluation)
            .where(WatchlistEvaluation.stock_id == stock_id)
            .order_by(WatchlistEvaluation.evaluated_at.asc())
        ).all()
    )

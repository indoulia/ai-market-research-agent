from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .models import Prediction, Stock

VALID_HORIZON_DAYS = (1, 3, 5, 7)

# Fields that constitute the original recommendation as issued; these must never
# change after creation so a stored recommendation can be evaluated later without
# being retrospectively altered. `status` is intentionally excluded: M1.5 will
# transition it as recommendations are evaluated.
IMMUTABLE_FIELDS = (
    "stock_id",
    "created_at",
    "as_of_timestamp",
    "entry_price",
    "horizon_days",
    "target_return",
    "stop_return",
    "predicted_probability",
    "confidence",
    "model_version",
    "feature_version",
    "consensus_contract_version",
    "horizon_selection_version",
    "scoring_contract_version",
    "opportunity_score",
)


class RecommendationImmutableError(RuntimeError):
    pass


@event.listens_for(Prediction, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationImmutableError(
            f"recommendation {target.id} field(s) {changed} cannot be modified after creation"
        )


def record_recommendation(
    session: Session,
    *,
    stock_id: int,
    as_of_timestamp: datetime,
    entry_price: Decimal,
    horizon_days: int,
    target_return: Decimal,
    stop_return: Decimal,
    predicted_probability: Decimal,
    confidence: Decimal,
    model_version: str,
    feature_version: str,
    consensus_contract_version: str,
    horizon_selection_version: str,
    scoring_contract_version: str,
    opportunity_score: Decimal,
) -> Prediction:
    if horizon_days not in VALID_HORIZON_DAYS:
        raise ValueError(f"horizon_days must be one of {VALID_HORIZON_DAYS}")
    recommendation = Prediction(
        stock_id=stock_id,
        created_at=datetime.now(timezone.utc),
        as_of_timestamp=as_of_timestamp,
        entry_price=entry_price,
        horizon_days=horizon_days,
        target_return=target_return,
        stop_return=stop_return,
        predicted_probability=predicted_probability,
        confidence=confidence,
        model_version=model_version,
        feature_version=feature_version,
        consensus_contract_version=consensus_contract_version,
        horizon_selection_version=horizon_selection_version,
        scoring_contract_version=scoring_contract_version,
        opportunity_score=opportunity_score,
        status="OPEN",
    )
    session.add(recommendation)
    session.flush()
    return recommendation


def get_recommendation_history(
    session: Session,
    *,
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Prediction]:
    query = session.query(Prediction).join(Stock, Prediction.stock_id == Stock.id)
    if symbol is not None:
        query = query.filter(Stock.symbol == symbol)
    if start is not None:
        query = query.filter(Prediction.as_of_timestamp >= start)
    if end is not None:
        query = query.filter(Prediction.as_of_timestamp <= end)
    return query.order_by(Prediction.as_of_timestamp.asc()).all()

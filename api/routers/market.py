"""GET /api/v1/market/summary (EPIC-M1.139)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.market import MarketSummary
from ..services.market import get_market_summary

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/summary", response_model=SuccessEnvelope[MarketSummary])
def get_summary(db: Session = Depends(get_db)):
    return success(get_market_summary(db))

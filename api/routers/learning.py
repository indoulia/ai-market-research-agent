"""GET /api/v1/learning/{summary,history,experiments} (EPIC-M3.9).

Exposes MRA's already-implemented learning-loop, champion/challenger and
experiment machinery (M1.31/M1.32/M1.53/M1.68/M1.69/M1.123) read-only --
see `api/services/learning.py`'s module docstring for exactly which
tables/functions are reused and why. No route here can trigger a learning
cycle, promotion, rollback or experiment run; every one is a pure GET over
already-persisted evidence (AC: "UI never directly modifies production
models")."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.learning import LearningExperiment, LearningHistoryEntry, LearningSummary
from ..services.learning import (
    DEFAULT_EXPERIMENTS_LIMIT,
    DEFAULT_HISTORY_LIMIT,
    MAX_EXPERIMENTS_LIMIT,
    MAX_HISTORY_LIMIT,
    get_learning_history,
    get_learning_summary,
    list_learning_experiments,
)

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/summary", response_model=SuccessEnvelope[LearningSummary])
def get_learning_summary_endpoint(db: Session = Depends(get_db)):
    return success(get_learning_summary(db))


@router.get("/history", response_model=SuccessEnvelope[list[LearningHistoryEntry]])
def get_learning_history_endpoint(
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT),
):
    return success(get_learning_history(db, limit=limit))


@router.get("/experiments", response_model=SuccessEnvelope[list[LearningExperiment]])
def get_learning_experiments_endpoint(
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_EXPERIMENTS_LIMIT, ge=1, le=MAX_EXPERIMENTS_LIMIT),
):
    return success(list_learning_experiments(db, limit=limit))

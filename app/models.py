from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, DateTime, Numeric, ForeignKey, JSON, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class Stock(Base):
    __tablename__ = "stocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    instrument_key: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")
    company_name: Mapped[str | None] = mapped_column(String(256))
    sector: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketPrice(Base):
    __tablename__ = "market_prices"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    volume: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(64))


class DatasetValidationRun(Base):
    __tablename__ = "dataset_validation_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    from_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    to_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    record_count: Mapped[int] = mapped_column(BigInteger)
    issue_count: Mapped[int] = mapped_column(BigInteger)
    report_json: Mapped[dict] = mapped_column(JSON)


class Prediction(Base):
    __tablename__ = "predictions"
    # BigInteger on sqlite doesn't get rowid-alias autoincrement, unlike Postgres BIGSERIAL;
    # the sqlite variant keeps local/test fixtures (see tests/test_recommendation_history.py) working.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    as_of_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    horizon_days: Mapped[int] = mapped_column(Integer)
    target_return: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    stop_return: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    predicted_probability: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    confidence: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    model_version: Mapped[str] = mapped_column(String(64))
    feature_version: Mapped[str] = mapped_column(String(64))
    consensus_contract_version: Mapped[str] = mapped_column(String(32))
    horizon_selection_version: Mapped[str] = mapped_column(String(32))
    scoring_contract_version: Mapped[str] = mapped_column(String(32))
    opportunity_score: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    status: Mapped[str] = mapped_column(String(32), default="OPEN")


class PredictionOutcome(Base):
    __tablename__ = "prediction_outcomes"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), unique=True)
    evaluation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    highest_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    lowest_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    closing_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    maximum_return: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    maximum_drawdown: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    actual_return: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    prediction_error: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    target_hit: Mapped[bool] = mapped_column(Boolean)
    stop_hit: Mapped[bool] = mapped_column(Boolean)
    outcome: Mapped[str] = mapped_column(String(32))


class DailyCandidateScan(Base):
    __tablename__ = "daily_candidate_scans"
    __table_args__ = (UniqueConstraint("scan_date", "universe_version", name="uq_scan_date_universe_version"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_date: Mapped[date] = mapped_column(Date)
    universe_version: Mapped[str] = mapped_column(String(32))
    eligible_count: Mapped[int] = mapped_column(Integer)
    excluded_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanCandidate(Base):
    __tablename__ = "scan_candidates"
    __table_args__ = (UniqueConstraint("scan_id", "stock_id", name="uq_scan_candidate_scan_stock"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    eligible: Mapped[bool] = mapped_column(Boolean)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64))
    predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    sma20_distance: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume_ratio_20d: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    atr_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    data_quality_passed: Mapped[bool | None] = mapped_column(Boolean)
    model_version: Mapped[str | None] = mapped_column(String(64))
    feature_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationGeneration(Base):
    __tablename__ = "recommendation_generations"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_candidate_id: Mapped[int] = mapped_column(ForeignKey("scan_candidates.id"), unique=True)
    outcome: Mapped[str] = mapped_column(String(16))
    consensus_contract_version: Mapped[str] = mapped_column(String(32))
    failed_criteria: Mapped[list | None] = mapped_column(JSON)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationSelection(Base):
    __tablename__ = "recommendation_selections"
    __table_args__ = (UniqueConstraint("scan_id", "recommendation_generation_id", name="uq_selection_scan_generation"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    recommendation_generation_id: Mapped[int] = mapped_column(ForeignKey("recommendation_generations.id"))
    rank: Mapped[int | None] = mapped_column(Integer)
    selected: Mapped[bool] = mapped_column(Boolean)
    selection_reason: Mapped[str] = mapped_column(String(32))
    selection_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationLifecycle(Base):
    __tablename__ = "recommendation_lifecycles"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    recommendation_generation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendation_generations.id"), unique=True
    )
    state: Mapped[str] = mapped_column(String(32))
    lifecycle_rule_version: Mapped[str] = mapped_column(String(32))
    outcome_id: Mapped[int | None] = mapped_column(ForeignKey("prediction_outcomes.id"))
    check_count: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64), unique=True)
    feature_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistEvaluation(Base):
    __tablename__ = "watchlist_evaluations"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consensus_contract_version: Mapped[str] = mapped_column(String(32))
    qualifies: Mapped[bool] = mapped_column(Boolean)
    failed_criteria: Mapped[list] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(32))
    backlog_reason: Mapped[str | None] = mapped_column(String(64))
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"))

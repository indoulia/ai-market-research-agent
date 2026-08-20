from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Numeric, ForeignKey, JSON, func
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


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64), unique=True)
    feature_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

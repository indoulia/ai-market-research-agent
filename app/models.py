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
    industry: Mapped[str | None] = mapped_column(String(128))
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
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


class DiscoveryRecord(Base):
    __tablename__ = "discovery_records"
    __table_args__ = (
        UniqueConstraint("scan_id", "stock_id", "source", name="uq_discovery_scan_stock_source"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    source: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(String(2000))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recommendation_generation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendation_generations.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiscoverySegment(Base):
    __tablename__ = "discovery_segments"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    discovery_record_id: Mapped[int] = mapped_column(ForeignKey("discovery_records.id"), unique=True)
    market_cap_bucket: Mapped[str] = mapped_column(String(32))
    sector: Mapped[str] = mapped_column(String(128))
    industry: Mapped[str] = mapped_column(String(128))
    liquidity_bucket: Mapped[str] = mapped_column(String(32))
    segmentation_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistDecision(Base):
    __tablename__ = "watchlist_decisions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    recommendation_generation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendation_generations.id"), unique=True
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16))
    failed_criteria: Mapped[list | None] = mapped_column(JSON)
    consensus_contract_version: Mapped[str] = mapped_column(String(32))
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"))
    model_version: Mapped[str | None] = mapped_column(String(64))
    feature_version: Mapped[str | None] = mapped_column(String(64))
    scoring_contract_version: Mapped[str | None] = mapped_column(String(32))
    horizon_selection_version: Mapped[str | None] = mapped_column(String(32))
    opportunity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    decision_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReplayRun(Base):
    __tablename__ = "replay_runs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    recommendation_generation_id: Mapped[int] = mapped_column(ForeignKey("recommendation_generations.id"))
    replayed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    limitation: Mapped[str | None] = mapped_column(String(64))
    replayed_qualifies: Mapped[bool | None] = mapped_column(Boolean)
    replayed_failed_criteria: Mapped[list | None] = mapped_column(JSON)
    replayed_opportunity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    replayed_horizon_days: Mapped[int | None] = mapped_column(Integer)
    replayed_predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    replayed_model_version: Mapped[str | None] = mapped_column(String(64))
    replayed_feature_version: Mapped[str | None] = mapped_column(String(64))
    replayed_consensus_contract_version: Mapped[str | None] = mapped_column(String(32))
    replayed_scoring_contract_version: Mapped[str | None] = mapped_column(String(32))
    replayed_horizon_selection_version: Mapped[str | None] = mapped_column(String(32))
    matches_original: Mapped[bool | None] = mapped_column(Boolean)
    replay_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketRegime(Base):
    __tablename__ = "market_regimes"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"), unique=True)
    regime: Mapped[str] = mapped_column(String(32))
    breadth_positive_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    average_atr_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    eligible_count: Mapped[int] = mapped_column(Integer)
    regime_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelPromotion(Base):
    __tablename__ = "model_promotions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    candidate_model_version: Mapped[str] = mapped_column(String(64))
    baseline_model_version: Mapped[str | None] = mapped_column(String(64))
    evidence_report_version: Mapped[str] = mapped_column(String(32))
    success_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    decision: Mapped[str] = mapped_column(String(16))
    decision_reason: Mapped[str] = mapped_column(String(64))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approver: Mapped[str] = mapped_column(String(128))
    promotion_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningCycle(Base):
    __tablename__ = "learning_cycles"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    new_outcomes_count: Mapped[int] = mapped_column(Integer)
    watermark_outcome_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"))
    outcome: Mapped[str] = mapped_column(String(32))
    skip_reason: Mapped[str | None] = mapped_column(String(64))
    discovery_effectiveness_version: Mapped[str | None] = mapped_column(String(32))
    calibration_candidate_version: Mapped[str | None] = mapped_column(String(32))
    candidate_model_evaluation_version: Mapped[str | None] = mapped_column(String(32))
    model_promotion_id: Mapped[int | None] = mapped_column(ForeignKey("model_promotions.id"))
    cycle_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataFetchAttempt(Base):
    __tablename__ = "data_fetch_attempts"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    data_type: Mapped[str] = mapped_column(String(32))
    scope_key: Mapped[str] = mapped_column(String(128))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    success: Mapped[bool] = mapped_column(Boolean)
    failure_reason: Mapped[str | None] = mapped_column(String(128))
    refresh_policy_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationObservation(Base):
    __tablename__ = "recommendation_observations"
    __table_args__ = (UniqueConstraint("prediction_id", "day_number", name="uq_observation_prediction_day"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    observation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    day_number: Mapped[int] = mapped_column(Integer)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    return_since_entry: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    data_available: Mapped[bool] = mapped_column(Boolean)
    horizon_complete: Mapped[bool] = mapped_column(Boolean)
    observation_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationRetirement(Base):
    __tablename__ = "recommendation_retirements"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), unique=True)
    retired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retirement_reason: Mapped[str] = mapped_column(String(32))
    lifecycle_state_at_retirement: Mapped[str] = mapped_column(String(32))
    retirement_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutcomeMeasurement(Base):
    __tablename__ = "outcome_measurements"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_outcome_id: Mapped[int] = mapped_column(ForeignKey("prediction_outcomes.id"), unique=True)
    outcome_classification: Mapped[str] = mapped_column(String(32))
    realized_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    measurement_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricalLearningRecord(Base):
    __tablename__ = "historical_learning_records"
    __table_args__ = (
        UniqueConstraint("dataset_version", "prediction_id", name="uq_learning_record_version_prediction"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(32))
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    information_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    opportunity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    sma20_distance: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume_ratio_20d: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    atr_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    horizon_days: Mapped[int] = mapped_column(Integer)
    market_regime: Mapped[str | None] = mapped_column(String(32))
    sector: Mapped[str | None] = mapped_column(String(128))
    market_cap_bucket: Mapped[str | None] = mapped_column(String(32))
    discovery_source: Mapped[str | None] = mapped_column(String(32))
    outcome_classification: Mapped[str | None] = mapped_column(String(32))
    realized_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    included: Mapped[bool] = mapped_column(Boolean)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64))
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


class ModelPromotionDecision(Base):
    __tablename__ = "model_promotion_decisions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(32))
    candidate_model_name: Mapped[str] = mapped_column(String(64))
    comparison_version: Mapped[str] = mapped_column(String(32))
    calibration_error_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    decision: Mapped[str] = mapped_column(String(16))
    decision_reason: Mapped[str] = mapped_column(String(64))
    regressed_segment_dimension: Mapped[str | None] = mapped_column(String(32))
    regressed_segment_key: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approver: Mapped[str] = mapped_column(String(128))
    promotion_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SelfLearningCycle(Base):
    __tablename__ = "self_learning_cycles"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    new_outcomes_count: Mapped[int] = mapped_column(Integer)
    watermark_outcome_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"))
    outcome: Mapped[str] = mapped_column(String(32))
    skip_reason: Mapped[str | None] = mapped_column(String(64))
    dataset_version: Mapped[str | None] = mapped_column(String(32))
    comparison_version: Mapped[str | None] = mapped_column(String(32))
    model_promotion_decision_id: Mapped[int | None] = mapped_column(ForeignKey("model_promotion_decisions.id"))
    discovery_triggered: Mapped[bool] = mapped_column(Boolean)
    cycle_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

from datetime import date, datetime, time
from decimal import Decimal
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, DateTime, Time, Numeric, ForeignKey, Index, JSON, UniqueConstraint, func
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
    # Mirrors migrations/versions/0001_initial.py's table-level constraint of the same
    # name -- previously undeclared here, so Base.metadata.create_all() (every sqlite
    # test fixture in this repo) silently omitted it, unlike the real migrated schema.
    __table_args__ = (UniqueConstraint("stock_id", "timestamp", name="uq_market_prices_stock_timestamp"),)
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
    label_methodology_version: Mapped[str | None] = mapped_column(String(32))


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
    provider_id: Mapped[str | None] = mapped_column(String(64))
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


class UserPreference(Base):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    horizon_band: Mapped[str] = mapped_column(String(16))
    custom_horizon_days: Mapped[int | None] = mapped_column(Integer)
    risk_preference: Mapped[str] = mapped_column(String(16))
    min_confidence_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    preferred_sectors: Mapped[list | None] = mapped_column(JSON)
    preferred_market_cap_buckets: Mapped[list | None] = mapped_column(JSON)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    preference_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationPreferenceSnapshot(Base):
    __tablename__ = "recommendation_preference_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "recommendation_generation_id", name="uq_pref_snapshot_user_generation"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    recommendation_generation_id: Mapped[int] = mapped_column(ForeignKey("recommendation_generations.id"))
    user_preference_id: Mapped[int] = mapped_column(ForeignKey("user_preferences.id"))
    horizon_band: Mapped[str] = mapped_column(String(16))
    min_confidence_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    matched_horizon: Mapped[bool] = mapped_column(Boolean)
    met_min_confidence: Mapped[bool] = mapped_column(Boolean)
    preference_match_boost: Mapped[bool] = mapped_column(Boolean)
    included: Mapped[bool] = mapped_column(Boolean)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64))
    snapshotted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    preference_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationPublication(Base):
    __tablename__ = "recommendation_publications"
    __table_args__ = (
        UniqueConstraint("prediction_id", "methodology_version", name="uq_publication_prediction_methodology"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    methodology_version: Mapped[str] = mapped_column(String(32))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    target_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    stop_loss_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    horizon_days: Mapped[int] = mapped_column(Integer)
    upside_percentage: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    downside_percentage: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    reward_risk_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    published: Mapped[bool] = mapped_column(Boolean)
    rejection_reason: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationEvidenceItem(Base):
    __tablename__ = "recommendation_evidence_items"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evidence_category", name="uq_evidence_prediction_category"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    evidence_category: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    source: Mapped[str | None] = mapped_column(String(64))
    reference: Mapped[str | None] = mapped_column(String(2000))
    evidence_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_stale: Mapped[bool] = mapped_column(Boolean)
    snapshot_rule_version: Mapped[str] = mapped_column(String(32))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConfidenceCalibrationRecord(Base):
    __tablename__ = "confidence_calibration_records"
    __table_args__ = (
        UniqueConstraint("prediction_id", "calibration_version", name="uq_confidence_calibration_prediction_version"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    calibration_version: Mapped[str] = mapped_column(String(32))
    raw_confidence: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    calibrated_confidence: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    bucket_lower: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    bucket_upper: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    sample_count: Mapped[int] = mapped_column(Integer)
    calibration_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    verdict: Mapped[str] = mapped_column(String(32))
    training_window_label: Mapped[str] = mapped_column(String(128))
    calibrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConfidenceQualityClassification(Base):
    __tablename__ = "confidence_quality_classifications"
    __table_args__ = (
        UniqueConstraint("prediction_id", "classification_rule_version", name="uq_confidence_quality_prediction_version"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    confidence_calibration_record_id: Mapped[int] = mapped_column(ForeignKey("confidence_calibration_records.id"))
    quality: Mapped[str] = mapped_column(String(32))
    reasons: Mapped[list] = mapped_column(JSON)
    sample_count: Mapped[int] = mapped_column(Integer)
    calibration_verdict: Mapped[str] = mapped_column(String(32))
    is_data_fresh: Mapped[bool] = mapped_column(Boolean)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    classification_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    user_id: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(String(2000))
    feedback_stage: Mapped[str] = mapped_column(String(16))
    model_version: Mapped[str] = mapped_column(String(64))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    feedback_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceRevalidationCheck(Base):
    __tablename__ = "evidence_revalidation_checks"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    recommendation_evidence_item_id: Mapped[int] = mapped_column(ForeignKey("recommendation_evidence_items.id"))
    evidence_category: Mapped[str] = mapped_column(String(32))
    horizon_days: Mapped[int] = mapped_column(Integer)
    freshness_threshold_seconds: Mapped[int] = mapped_column(Integer)
    revalidation_required: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(32))
    original_value: Mapped[str | None] = mapped_column(String(64))
    current_value: Mapped[str | None] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revalidation_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationRevision(Base):
    __tablename__ = "recommendation_revisions"
    __table_args__ = (
        UniqueConstraint("previous_prediction_id", name="uq_revision_previous_prediction"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    original_prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    previous_prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    revised_prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    revision_reason: Mapped[str] = mapped_column(String(32))
    triggering_evidence_revalidation_check_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_revalidation_checks.id")
    )
    revised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningPipelinePromotionDecision(Base):
    __tablename__ = "learning_pipeline_promotion_decisions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    source_signal: Mapped[str] = mapped_column(String(32))
    affected_condition: Mapped[str] = mapped_column(String(256))
    candidate_version: Mapped[str] = mapped_column(String(32))
    sample_size: Mapped[int] = mapped_column(Integer)
    expected_impact: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    decision: Mapped[str] = mapped_column(String(32))
    decision_reason: Mapped[str] = mapped_column(String(64))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approver: Mapped[str] = mapped_column(String(128))
    gate_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PositionRiskAssessment(Base):
    __tablename__ = "position_risk_assessments"
    __table_args__ = (
        UniqueConstraint("prediction_id", "assessment_rule_version", name="uq_position_risk_prediction_version"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    recommendation_publication_id: Mapped[int] = mapped_column(ForeignKey("recommendation_publications.id"))
    risk_percentage: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    reward_percentage: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    reward_risk_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    atr_percent: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    risk_in_atr_units: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    reward_in_atr_units: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    horizon_days: Mapped[int] = mapped_column(Integer)
    horizon_consistent: Mapped[bool] = mapped_column(Boolean)
    inconsistency_reason: Mapped[str | None] = mapped_column(String(64))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assessment_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserHolding(Base):
    __tablename__ = "user_holdings"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    action: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserAllocationLimit(Base):
    __tablename__ = "user_allocation_limits"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    max_position_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    max_sector_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    limit_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MultiHorizonResolution(Base):
    __tablename__ = "multi_horizon_resolutions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    primary_prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    primary_horizon_days: Mapped[int] = mapped_column(Integer)
    conflicting_prediction_ids: Mapped[list] = mapped_column(JSON)
    has_conflict: Mapped[bool] = mapped_column(Boolean)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolution_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationRevalidationOutcome(Base):
    __tablename__ = "recommendation_revalidation_outcomes"
    __table_args__ = (
        UniqueConstraint("prediction_id", "checked_at", name="uq_revalidation_prediction_checked_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    outcome: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(256))
    elapsed_days: Mapped[int] = mapped_column(Integer)
    current_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    evidence_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revalidation_engine_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserAlertPreference(Base):
    __tablename__ = "user_alert_preferences"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    muted_alert_types: Mapped[list] = mapped_column(JSON)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    alert_preference_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationAlert(Base):
    __tablename__ = "recommendation_alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "alert_type", "source_table", "source_id", name="uq_alert_user_type_source"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    alert_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"))
    source_table: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"))
    message: Mapped[str] = mapped_column(String(512))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    alert_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceConflictResolution(Base):
    __tablename__ = "evidence_conflict_resolutions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "resolved_at", name="uq_conflict_resolution_prediction_resolved_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    state: Mapped[str] = mapped_column(String(32))
    conflict_count: Mapped[int] = mapped_column(Integer)
    conflicts: Mapped[list] = mapped_column(JSON)
    evidence_categories_considered: Mapped[list] = mapped_column(JSON)
    confidence_adjustment_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    blocks_qualification: Mapped[bool] = mapped_column(Boolean)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolution_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationDecisionTrace(Base):
    __tablename__ = "recommendation_decision_traces"
    __table_args__ = (
        UniqueConstraint("recommendation_generation_id", name="uq_decision_trace_generation"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    recommendation_generation_id: Mapped[int] = mapped_column(ForeignKey("recommendation_generations.id"))
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    as_of_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sma20_distance: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume_ratio_20d: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    atr_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    target_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    stop_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    opportunity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    model_version: Mapped[str | None] = mapped_column(String(64))
    feature_version: Mapped[str | None] = mapped_column(String(64))
    consensus_contract_version: Mapped[str | None] = mapped_column(String(32))
    horizon_selection_version: Mapped[str | None] = mapped_column(String(32))
    scoring_contract_version: Mapped[str | None] = mapped_column(String(32))
    target_stop_methodology_version: Mapped[str | None] = mapped_column(String(32))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    qualification_outcome: Mapped[str] = mapped_column(String(32))
    rejection_reasons: Mapped[list | None] = mapped_column(JSON)
    evidence_categories_snapshot: Mapped[list] = mapped_column(JSON)
    traced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decision_trace_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRegressionCheck(Base):
    __tablename__ = "model_regression_checks"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64))
    baseline_window_label: Mapped[str] = mapped_column(String(128))
    baseline_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    baseline_sample_count: Mapped[int] = mapped_column(Integer)
    monitoring_window_label: Mapped[str] = mapped_column(String(128))
    monitoring_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    monitoring_sample_count: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(32))
    segment_regressions: Mapped[list] = mapped_column(JSON)
    rollback_triggered: Mapped[bool] = mapped_column(Boolean)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detection_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (UniqueConstraint("name", name="uq_experiment_name"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    hypothesis: Mapped[str] = mapped_column(String(2048))
    experiment_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentArm(Base):
    __tablename__ = "experiment_arms"
    __table_args__ = (UniqueConstraint("experiment_id", "arm_name", name="uq_experiment_arm_name"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    arm_name: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(64))
    window_label: Mapped[str] = mapped_column(String(128))
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    horizon_days_filter: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentResult(Base):
    __tablename__ = "experiment_results"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    experiment_arm_id: Mapped[int] = mapped_column(ForeignKey("experiment_arms.id"))
    sample_count: Mapped[int] = mapped_column(Integer)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    calibration_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    consistency_stdev: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    arm_config_snapshot: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    framework_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackDrivenExperiment(Base):
    __tablename__ = "feedback_driven_experiments"
    __table_args__ = (
        UniqueConstraint("experiment_id", name="uq_feedback_driven_experiment_experiment"),
        UniqueConstraint("feedback_category", "feedback_reason_code", name="uq_feedback_driven_experiment_pattern"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    feedback_category: Mapped[str] = mapped_column(String(64))
    feedback_reason_code: Mapped[str] = mapped_column(String(64))
    evaluated_count_at_creation: Mapped[int] = mapped_column(Integer)
    distinct_user_count_at_creation: Mapped[int] = mapped_column(Integer)
    repeated_prediction_count_at_creation: Mapped[int] = mapped_column(Integer)
    success_rate_at_creation: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    pipeline_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserPreferenceSuggestion(Base):
    __tablename__ = "user_preference_suggestions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    current_horizon_band: Mapped[str | None] = mapped_column(String(32))
    suggested_horizon_band: Mapped[str] = mapped_column(String(32))
    evidence_sample_count: Mapped[int] = mapped_column(Integer)
    evidence_agree_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    current_band_agree_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    rationale: Mapped[str] = mapped_column(String(1024))
    suggested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    learning_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserDecision(Base):
    __tablename__ = "user_decisions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    recommendation_generation_id: Mapped[int] = mapped_column(ForeignKey("recommendation_generations.id"))
    decision: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str | None] = mapped_column(String(2000))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    journal_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FundamentalDataRecord(Base):
    __tablename__ = "fundamental_data_records"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    source: Mapped[str] = mapped_column(String(64))
    period_end_date: Mapped[date | None] = mapped_column(Date)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    eps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    operating_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    net_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    free_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    price_to_book: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingestion_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceQualityDecision(Base):
    __tablename__ = "evidence_quality_decisions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_evidence_quality_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    state: Mapped[str] = mapped_column(String(32))
    available_category_count: Mapped[int] = mapped_column(Integer)
    stale_category_count: Mapped[int] = mapped_column(Integer)
    unavailable_category_count: Mapped[int] = mapped_column(Integer)
    categories_considered: Mapped[list] = mapped_column(JSON)
    leaked_categories: Mapped[list] = mapped_column(JSON)
    reasons: Mapped[list] = mapped_column(JSON)
    confidence_adjustment_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    blocks_publication: Mapped[bool] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gate_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HorizonProbabilityProfile(Base):
    __tablename__ = "horizon_probability_profiles"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer)
    positive_return_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    target_hit_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    stop_hit_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    expected_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    downside_p10_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    profile_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionTrustScore(Base):
    __tablename__ = "prediction_trust_scores"
    __table_args__ = (
        UniqueConstraint("prediction_id", "computed_at", name="uq_prediction_trust_score_prediction_computed_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    overall_trust_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    trust_quality: Mapped[str] = mapped_column(String(32))
    calibration_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    historical_accuracy_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    recent_performance_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    horizon_reliability_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    regime_reliability_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    evidence_quality_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    available_component_count: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trust_score_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyPredictionSnapshot(Base):
    __tablename__ = "daily_prediction_snapshots"
    __table_args__ = (
        Index("ix_daily_prediction_snapshots_prediction_date", "prediction_id", "snapshot_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    recommendation_decision_trace_id: Mapped[int | None] = mapped_column(ForeignKey("recommendation_decision_traces.id"))
    prediction_trust_score_id: Mapped[int | None] = mapped_column(ForeignKey("prediction_trust_scores.id"))
    snapshot_date: Mapped[date] = mapped_column(Date)
    is_canonical: Mapped[bool] = mapped_column(Boolean)
    snapshotted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HorizonRegimeTrust(Base):
    __tablename__ = "horizon_regime_trusts"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    segment_type: Mapped[str] = mapped_column(String(16))
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    regime: Mapped[str | None] = mapped_column(String(32))
    sample_count: Mapped[int] = mapped_column(Integer)
    success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    success_rate_standard_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    is_low_trust: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trust_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionCalibrationDrift(Base):
    __tablename__ = "prediction_calibration_drifts"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    baseline_window_label: Mapped[str] = mapped_column(String(128))
    baseline_sample_count: Mapped[int] = mapped_column(Integer)
    monitoring_window_label: Mapped[str] = mapped_column(String(128))
    monitoring_sample_count: Mapped[int] = mapped_column(Integer)
    baseline_mean_predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    monitoring_mean_predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    distribution_drift: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    distribution_drift_detected: Mapped[bool] = mapped_column(Boolean)
    baseline_calibration_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    monitoring_calibration_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    calibration_drift: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    calibration_drift_detected: Mapped[bool] = mapped_column(Boolean)
    model_regression_check_id: Mapped[int | None] = mapped_column(ForeignKey("model_regression_checks.id"))
    verdict: Mapped[str] = mapped_column(String(32))
    trust_reduction_recommended: Mapped[bool] = mapped_column(Boolean)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    drift_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PositiveRecommendationGateDecision(Base):
    __tablename__ = "positive_recommendation_gate_decisions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_positive_gate_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    verdict: Mapped[str] = mapped_column(String(32))
    evidence_quality_met: Mapped[bool] = mapped_column(Boolean)
    trust_quality_met: Mapped[bool] = mapped_column(Boolean)
    segment_trust_met: Mapped[bool] = mapped_column(Boolean)
    calibration_drift_met: Mapped[bool] = mapped_column(Boolean)
    suppression_reasons: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gate_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsEventRecord(Base):
    __tablename__ = "news_event_records"
    __table_args__ = (UniqueConstraint("stock_id", "external_id", name="uq_news_event_stock_external_id"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128))
    headline: Mapped[str] = mapped_column(String(512))
    event_type: Mapped[str] = mapped_column(String(32))
    materiality: Mapped[str] = mapped_column(String(16))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingestion_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionQualityBenchmarkReport(Base):
    __tablename__ = "prediction_quality_benchmark_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    window_label: Mapped[str] = mapped_column(String(128))
    sample_count: Mapped[int] = mapped_column(Integer)
    directional_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    target_hit_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    stop_hit_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_expected_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_realized_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_max_favorable_excursion: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_max_adverse_excursion: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_time_to_exit_days: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    benchmark_stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"))
    avg_benchmark_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    avg_excess_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    benchmark_coverage_count: Mapped[int] = mapped_column(Integer)
    benchmark_verdict: Mapped[str] = mapped_column(String(32))
    segment_breakdown: Mapped[list] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(32))
    trust_reduction_recommended: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    benchmark_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionStabilityAssessment(Base):
    __tablename__ = "prediction_stability_assessments"
    __table_args__ = (
        UniqueConstraint("original_prediction_id", "assessed_at", name="uq_stability_prediction_assessed_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    original_prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    revision_count: Mapped[int] = mapped_column(Integer)
    max_score_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    max_confidence_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    unexplained_revision_count: Mapped[int] = mapped_column(Integer)
    stability_verdict: Mapped[str] = mapped_column(String(32))
    model_agreement_verdict: Mapped[str] = mapped_column(String(32))
    model_agreement_score_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    stability_backed_by_outcomes: Mapped[bool] = mapped_column(Boolean)
    trust_reduction_recommended: Mapped[bool] = mapped_column(Boolean)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assessment_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrustControlDecision(Base):
    __tablename__ = "trust_control_decisions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_trust_control_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    overall_trust_quality: Mapped[str] = mapped_column(String(32))
    eligibility_reduced: Mapped[bool] = mapped_column(Boolean)
    segment_trust_ok: Mapped[bool] = mapped_column(Boolean)
    calibration_drift_ok: Mapped[bool] = mapped_column(Boolean)
    benchmark_performance_ok: Mapped[bool] = mapped_column(Boolean)
    stability_ok: Mapped[bool] = mapped_column(Boolean)
    causes: Mapped[list] = mapped_column(JSON)
    recommended_action: Mapped[str] = mapped_column(String(32))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    control_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionAttributionSnapshot(Base):
    __tablename__ = "prediction_attribution_snapshots"
    __table_args__ = (UniqueConstraint("prediction_id", name="uq_attribution_snapshot_prediction"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    model_version: Mapped[str] = mapped_column(String(64))
    horizon_days: Mapped[int] = mapped_column(Integer)
    regime: Mapped[str | None] = mapped_column(String(32))
    sma20_distance_bucket: Mapped[str | None] = mapped_column(String(16))
    volume_ratio_bucket: Mapped[str | None] = mapped_column(String(16))
    evidence_categories_available: Mapped[list] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(32))
    snapshotted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attribution_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactorAssociationReport(Base):
    __tablename__ = "factor_association_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scope_label: Mapped[str] = mapped_column(String(128))
    sample_count: Mapped[int] = mapped_column(Integer)
    baseline_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    factor_associations: Mapped[list] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionUsefulnessAssessment(Base):
    __tablename__ = "prediction_usefulness_assessments"
    __table_args__ = (UniqueConstraint("prediction_id", name="uq_usefulness_assessment_prediction"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    directional_outcome: Mapped[str] = mapped_column(String(32))
    risk_adjusted_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    usefulness_verdict: Mapped[str] = mapped_column(String(32))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usefulness_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HorizonUsefulnessReport(Base):
    __tablename__ = "horizon_usefulness_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer)
    avg_risk_adjusted_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    useful_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorporateAction(Base):
    __tablename__ = "corporate_actions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    effective_date: Mapped[date] = mapped_column(Date)
    ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    old_symbol: Mapped[str | None] = mapped_column(String(32))
    new_symbol: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(64))
    action_version: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BiasGuardCheck(Base):
    __tablename__ = "bias_guard_checks"
    __table_args__ = (
        UniqueConstraint("prediction_id", "workflow_type", "checked_at", name="uq_bias_guard_prediction_workflow_checked_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    workflow_type: Mapped[str] = mapped_column(String(32))
    verdict: Mapped[str] = mapped_column(String(16))
    reason_codes: Mapped[list] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    guard_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BiasGuardOverride(Base):
    __tablename__ = "bias_guard_overrides"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("bias_guard_checks.id"), unique=True)
    justification: Mapped[str] = mapped_column(String(1024))
    authorized_by: Mapped[str] = mapped_column(String(128))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    override_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExecutionCostAssessment(Base):
    __tablename__ = "execution_cost_assessments"
    __table_args__ = (UniqueConstraint("prediction_id", name="uq_execution_cost_prediction"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    gross_return: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    liquidity_bucket: Mapped[str] = mapped_column(String(32))
    executability_verdict: Mapped[str] = mapped_column(String(32))
    estimated_cost_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    net_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    cost_model_version: Mapped[str] = mapped_column(String(32))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PositiveOpportunityRanking(Base):
    __tablename__ = "positive_opportunity_rankings"
    __table_args__ = (UniqueConstraint("prediction_id", "evaluated_at", name="uq_opportunity_ranking_prediction_evaluated_at"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    horizon_days: Mapped[int] = mapped_column(Integer)
    composite_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    expected_return_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    probability_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    trust_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    reward_risk_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    evidence_quality_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    stability_component: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    rank_position: Mapped[int | None] = mapped_column(Integer)
    included: Mapped[bool] = mapped_column(Boolean)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ranking_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningHypothesis(Base):
    __tablename__ = "learning_hypotheses"
    __table_args__ = (
        UniqueConstraint(
            "model_version", "hypothesis_category", "dimension", "factor_value", "generated_at",
            name="uq_learning_hypothesis_segment_generated_at",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    hypothesis_category: Mapped[str] = mapped_column(String(32))
    dimension: Mapped[str] = mapped_column(String(64))
    factor_value: Mapped[str] = mapped_column(String(64))
    baseline_window_label: Mapped[str] = mapped_column(String(64))
    monitoring_window_label: Mapped[str] = mapped_column(String(64))
    baseline_sample_count: Mapped[int] = mapped_column(Integer)
    monitoring_sample_count: Mapped[int] = mapped_column(Integer)
    baseline_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    monitoring_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    proposed_action: Mapped[str] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(String(32))
    eligibility_effect: Mapped[str] = mapped_column(String(32))
    evidence_reference: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hypothesis_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RankingEffectivenessReport(Base):
    __tablename__ = "ranking_effectiveness_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    window_label: Mapped[str] = mapped_column(String(128))
    top_k: Mapped[int] = mapped_column(Integer)
    composite_sample_count: Mapped[int] = mapped_column(Integer)
    composite_success_count: Mapped[int] = mapped_column(Integer)
    composite_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    alternative_sample_count: Mapped[int] = mapped_column(Integer)
    alternative_success_count: Mapped[int] = mapped_column(Integer)
    alternative_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    success_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effectiveness_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HoldoutWindowRegistry(Base):
    __tablename__ = "holdout_window_registry"
    __table_args__ = (UniqueConstraint("label", name="uq_holdout_window_label"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    label: Mapped[str] = mapped_column(String(128))
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registry_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HoldoutUsageRecord(Base):
    __tablename__ = "holdout_usage_records"
    __table_args__ = (UniqueConstraint("holdout_label", name="uq_holdout_usage_label"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    holdout_label: Mapped[str] = mapped_column(String(128))
    experiment_arm_id: Mapped[int] = mapped_column(ForeignKey("experiment_arms.id"))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MultiplicityGuardDecision(Base):
    __tablename__ = "multiplicity_guard_decisions"
    __table_args__ = (
        UniqueConstraint("model_version", "evaluated_at", name="uq_multiplicity_guard_model_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    trial_count: Mapped[int] = mapped_column(Integer)
    observed_success_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    weakness_margin: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    adjusted_margin: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    significant: Mapped[bool] = mapped_column(Boolean)
    verdict: Mapped[str] = mapped_column(String(32))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    guard_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndependentConfirmationDecision(Base):
    __tablename__ = "independent_confirmation_decisions"
    __table_args__ = (
        UniqueConstraint("model_version", "confirmed_at", name="uq_independent_confirmation_model_confirmed_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    baseline_window_label: Mapped[str] = mapped_column(String(128))
    first_window_label: Mapped[str] = mapped_column(String(128))
    confirmation_window_label: Mapped[str] = mapped_column(String(128))
    first_window_verdict: Mapped[str] = mapped_column(String(32))
    confirmation_window_verdict: Mapped[str] = mapped_column(String(32))
    both_validated: Mapped[bool] = mapped_column(Boolean)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmation_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ValidationFold(Base):
    __tablename__ = "validation_folds"
    __table_args__ = (
        UniqueConstraint("model_version", "fold_index", "computed_at", name="uq_validation_fold_model_index_computed_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    fold_index: Mapped[int] = mapped_column(Integer)
    train_window_label: Mapped[str] = mapped_column(String(128))
    train_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    train_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_window_label: Mapped[str] = mapped_column(String(128))
    validation_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    validation_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    embargo_days: Mapped[int] = mapped_column(Integer)
    eligible_training_prediction_ids: Mapped[list] = mapped_column(JSON)
    excluded_prediction_ids: Mapped[list] = mapped_column(JSON)
    exclusion_reason_counts: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    framework_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TemporalValidationPolicyDecision(Base):
    __tablename__ = "temporal_validation_policy_decisions"
    __table_args__ = (
        UniqueConstraint("model_version", "evaluated_at", name="uq_temporal_validation_policy_model_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    fold_ids: Mapped[list] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(16))
    fail_reasons: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeatureReferenceDistribution(Base):
    __tablename__ = "feature_reference_distributions"
    __table_args__ = (
        UniqueConstraint("model_version", "feature_name", name="uq_feature_reference_model_feature"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    feature_name: Mapped[str] = mapped_column(String(64))
    window_label: Mapped[str] = mapped_column(String(128))
    sample_count: Mapped[int] = mapped_column(Integer)
    mean: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    stdev: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reference_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeatureDriftAssessment(Base):
    __tablename__ = "feature_drift_assessments"
    __table_args__ = (
        UniqueConstraint("model_version", "feature_name", "evaluated_at", name="uq_feature_drift_model_feature_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    feature_name: Mapped[str] = mapped_column(String(64))
    monitoring_window_label: Mapped[str] = mapped_column(String(128))
    monitoring_sample_count: Mapped[int] = mapped_column(Integer)
    monitoring_mean: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    drift_magnitude: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    verdict: Mapped[str] = mapped_column(String(32))
    trust_reduction_recommended: Mapped[bool] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    drift_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegimeTransitionAssessment(Base):
    __tablename__ = "regime_transition_assessments"
    __table_args__ = (UniqueConstraint("scan_id", name="uq_regime_transition_scan"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    previous_scan_id: Mapped[int | None] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    current_regime: Mapped[str] = mapped_column(String(32))
    previous_regime: Mapped[str | None] = mapped_column(String(32))
    transition_detected: Mapped[bool] = mapped_column(Boolean)
    distance_to_boundary: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    boundary_instability_verdict: Mapped[str] = mapped_column(String(32))
    uncertainty_source: Mapped[str] = mapped_column(String(32))
    trust_reduction_recommended: Mapped[bool] = mapped_column(Boolean)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assessment_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionRegimeUncertaintySnapshot(Base):
    __tablename__ = "prediction_regime_uncertainty_snapshots"
    __table_args__ = (UniqueConstraint("prediction_id", name="uq_regime_uncertainty_snapshot_prediction"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    regime_transition_assessment_id: Mapped[int] = mapped_column(ForeignKey("regime_transition_assessments.id"))
    snapshotted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransitionPeriodPerformanceReport(Base):
    __tablename__ = "transition_period_performance_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    window_label: Mapped[str] = mapped_column(String(128))
    transition_sample_count: Mapped[int] = mapped_column(Integer)
    transition_success_count: Mapped[int] = mapped_column(Integer)
    transition_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    stable_sample_count: Mapped[int] = mapped_column(Integer)
    stable_success_count: Mapped[int] = mapped_column(Integer)
    stable_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    success_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FundamentalConsensusAssessment(Base):
    __tablename__ = "fundamental_consensus_assessments"
    __table_args__ = (
        UniqueConstraint("stock_id", "period_end_date", "evaluated_at", name="uq_fundamental_consensus_stock_period_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    period_end_date: Mapped[date] = mapped_column(Date)
    metric_name: Mapped[str] = mapped_column(String(32))
    source_count: Mapped[int] = mapped_column(Integer)
    sources_considered: Mapped[list] = mapped_column(JSON)
    weighted_mean: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    max_relative_deviation: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    trust_reduction_recommended: Mapped[bool] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consensus_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsConsensusAssessment(Base):
    __tablename__ = "news_consensus_assessments"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    anchor_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    distinct_source_count: Mapped[int] = mapped_column(Integer)
    distinct_headline_count: Mapped[int] = mapped_column(Integer)
    record_count: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(32))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consensus_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SegmentCalibrationAssessment(Base):
    __tablename__ = "segment_calibration_assessments"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_segment_calibration_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    resolved_segment_level: Mapped[str] = mapped_column(String(32))
    resolved_segment_key: Mapped[str] = mapped_column(String(128))
    resolved_sample_count: Mapped[int] = mapped_column(Integer)
    predicted_mean: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    observed_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    calibration_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    fallback_chain: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calibration_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionFreshnessDecision(Base):
    __tablename__ = "prediction_freshness_decisions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_prediction_freshness_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    revalidation_outcome: Mapped[str] = mapped_column(String(32))
    triggers: Mapped[list] = mapped_column(JSON)
    re_analysis_recommended: Mapped[bool] = mapped_column(Boolean)
    revision_trigger_reason: Mapped[str | None] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    engine_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventTriggerRecord(Base):
    __tablename__ = "event_trigger_records"
    __table_args__ = (
        UniqueConstraint("event_type", "source_table", "source_id", name="uq_event_trigger_source"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    source_table: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    materiality_note: Mapped[str | None] = mapped_column(String(64))
    affected_prediction_count: Mapped[int] = mapped_column(Integer)
    triggered_decision_ids: Mapped[list] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StockBehaviorAssessment(Base):
    __tablename__ = "stock_behavior_assessments"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "model_version", "horizon_days", "regime", "evaluated_at",
            name="uq_stock_behavior_stock_model_horizon_regime_evaluated_at",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    horizon_days: Mapped[int] = mapped_column(Integer)
    regime: Mapped[str | None] = mapped_column(String(32))
    resolved_level: Mapped[str] = mapped_column(String(32))
    resolved_sample_count: Mapped[int] = mapped_column(Integer)
    observed_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    fallback_chain: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    behavior_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SetupCombinationReport(Base):
    __tablename__ = "setup_combination_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    sample_count: Mapped[int] = mapped_column(Integer)
    combination_count_considered: Mapped[int] = mapped_column(Integer)
    multiplicity_trial_count: Mapped[int] = mapped_column(Integer)
    adjusted_margin: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    combinations: Mapped[list] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SectorRelativeAssessment(Base):
    __tablename__ = "sector_relative_assessments"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_sector_relative_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    sector: Mapped[str] = mapped_column(String(128))
    peer_group_size: Mapped[int] = mapped_column(Integer)
    peer_stock_ids: Mapped[list] = mapped_column(JSON)
    target_momentum: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    peer_mean_momentum: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    peer_momentum_stdev: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    relative_momentum_zscore: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assessment_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SectorPerformanceReport(Base):
    __tablename__ = "sector_performance_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    sector: Mapped[str] = mapped_column(String(128), index=True)
    window_label: Mapped[str] = mapped_column(String(128))
    sector_sample_count: Mapped[int] = mapped_column(Integer)
    sector_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    baseline_sample_count: Mapped[int] = mapped_column(Integer)
    baseline_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionLifecycleSnapshot(Base):
    __tablename__ = "prediction_lifecycle_snapshots"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_prediction_lifecycle_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    state: Mapped[str] = mapped_column(String(32))
    previous_state: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(256))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lifecycle_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CapacityControlDecision(Base):
    __tablename__ = "capacity_control_decisions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_capacity_control_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    rank_position: Mapped[int | None] = mapped_column(Integer)
    capacity_limit: Mapped[int] = mapped_column(Integer)
    included: Mapped[bool] = mapped_column(Boolean)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishedVsSuppressedReport(Base):
    __tablename__ = "published_vs_suppressed_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    window_label: Mapped[str] = mapped_column(String(128))
    published_sample_count: Mapped[int] = mapped_column(Integer)
    published_success_count: Mapped[int] = mapped_column(Integer)
    published_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    suppressed_sample_count: Mapped[int] = mapped_column(Integer)
    suppressed_success_count: Mapped[int] = mapped_column(Integer)
    suppressed_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    success_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    opportunity_cost_total: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    avoided_loss_total: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssumptionDecayAssessment(Base):
    __tablename__ = "assumption_decay_assessments"
    __table_args__ = (
        UniqueConstraint("prediction_id", "evaluated_at", name="uq_assumption_decay_prediction_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    tracked_categories: Mapped[list] = mapped_column(JSON)
    decayed_categories: Mapped[list] = mapped_column(JSON)
    decay_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    invalidation_recommended: Mapped[bool] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decay_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpecializationRoutingDecision(Base):
    __tablename__ = "specialization_routing_decisions"
    __table_args__ = (
        UniqueConstraint(
            "dimension", "segment_key", "specialized_model_version", "global_model_version", "computed_at",
            name="uq_specialization_routing_segment_models_computed_at",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(32))
    segment_key: Mapped[str] = mapped_column(String(64))
    specialized_model_version: Mapped[str] = mapped_column(String(64))
    global_model_version: Mapped[str] = mapped_column(String(64))
    candidate_count: Mapped[int] = mapped_column(Integer)
    adjusted_margin: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    baseline_window_label: Mapped[str] = mapped_column(String(128))
    confirmation_window_label: Mapped[str] = mapped_column(String(128))
    baseline_verdict: Mapped[str] = mapped_column(String(32))
    confirmation_verdict: Mapped[str] = mapped_column(String(32))
    specialized_sample_count: Mapped[int] = mapped_column(Integer)
    global_sample_count: Mapped[int] = mapped_column(Integer)
    routing_verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    routing_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProviderOutageSnapshot(Base):
    __tablename__ = "provider_outage_snapshots"
    __table_args__ = (
        UniqueConstraint("data_type", "evaluated_at", name="uq_provider_outage_data_type_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    data_type: Mapped[str] = mapped_column(String(32), index=True)
    total_registered_providers: Mapped[int] = mapped_column(Integer)
    healthy_provider_count: Mapped[int] = mapped_column(Integer)
    degraded_provider_count: Mapped[int] = mapped_column(Integer)
    degraded_provider_ids: Mapped[list] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(16))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReproducibilityAuditDecision(Base):
    __tablename__ = "reproducibility_audit_decisions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "audited_at", name="uq_reproducibility_audit_prediction_audited_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    version_drifted_fields: Mapped[list] = mapped_column(JSON)
    provider_drifted_categories: Mapped[list] = mapped_column(JSON)
    reproducible: Mapped[bool] = mapped_column(Boolean)
    audited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    audit_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CostQualityTradeoffReport(Base):
    __tablename__ = "cost_quality_tradeoff_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    data_type: Mapped[str] = mapped_column(String(32), index=True)
    provider_candidates: Mapped[list] = mapped_column(JSON)
    recommended_provider_id: Mapped[str | None] = mapped_column(String(64))
    best_free_provider_id: Mapped[str | None] = mapped_column(String(64))
    quality_floor: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProbabilisticScoreReport(Base):
    __tablename__ = "probabilistic_score_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    window_label: Mapped[str] = mapped_column(String(128))
    sample_count: Mapped[int] = mapped_column(Integer)
    brier_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    log_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReleaseReadinessReport(Base):
    __tablename__ = "release_readiness_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    check_results: Mapped[list] = mapped_column(JSON)
    blocking_issues: Mapped[list] = mapped_column(JSON)
    overall_verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CoverageDriftAssessment(Base):
    __tablename__ = "coverage_drift_assessments"
    __table_args__ = (
        UniqueConstraint("model_version", "evaluated_at", name="uq_coverage_drift_model_evaluated_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    reference_window_label: Mapped[str] = mapped_column(String(128))
    monitoring_window_label: Mapped[str] = mapped_column(String(128))
    reference_sample_count: Mapped[int] = mapped_column(Integer)
    monitoring_sample_count: Mapped[int] = mapped_column(Integer)
    reference_coverage_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    monitoring_coverage_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    coverage_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    trust_reduction_recommended: Mapped[bool] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    drift_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserApiPreferenceProfile(Base):
    __tablename__ = "user_api_preference_profiles"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    markets: Mapped[list] = mapped_column(JSON)
    industries: Mapped[list] = mapped_column(JSON)
    watchlist_symbols: Mapped[list] = mapped_column(JSON)
    notification_preferences: Mapped[dict] = mapped_column(JSON)
    display_preferences: Mapped[dict] = mapped_column(JSON)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    preference_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackIdempotencyKey(Base):
    __tablename__ = "feedback_idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_feedback_idem_user_key"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(256))
    feedback_id: Mapped[int] = mapped_column(ForeignKey("recommendation_feedback.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    session_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_session_id: Mapped[int | None] = mapped_column(ForeignKey("auth_sessions.id"))
    session_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionReliabilityAssessment(Base):
    __tablename__ = "prediction_reliability_assessments"
    __table_args__ = (
        UniqueConstraint("prediction_id", "assessed_at", name="uq_prediction_reliability_prediction_assessed_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    resolved_segment_level: Mapped[str] = mapped_column(String(32))
    resolved_sample_count: Mapped[int] = mapped_column(Integer)
    observed_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    confidence_interval_lower: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    confidence_interval_upper: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    confidence_interval_half_width: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    evidence_strength: Mapped[str] = mapped_column(String(32))
    uncertainty_source: Mapped[str | None] = mapped_column(String(32))
    data_uncertain: Mapped[bool] = mapped_column(Boolean)
    reliable: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list] = mapped_column(JSON)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reliability_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SegmentAbstentionQualityReport(Base):
    __tablename__ = "segment_abstention_quality_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    window_label: Mapped[str] = mapped_column(String(128))
    sample_count: Mapped[int] = mapped_column(Integer)
    segment_breakdown: Mapped[list] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrchestrationExecutionLock(Base):
    __tablename__ = "orchestration_execution_locks"
    __table_args__ = (
        UniqueConstraint("operation_name", "scope_key", name="uq_orchestration_lock_operation_scope"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    operation_name: Mapped[str] = mapped_column(String(64))
    scope_key: Mapped[str] = mapped_column(String(128))
    trigger_type: Mapped[str] = mapped_column(String(32))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    orchestration_rule_version: Mapped[str] = mapped_column(String(32))


class OrchestrationExecution(Base):
    __tablename__ = "orchestration_executions"
    __table_args__ = (
        Index("ix_orchestration_executions_dedup_key", "dedup_key"),
        Index("ix_orchestration_executions_operation_name", "operation_name"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    operation_name: Mapped[str] = mapped_column(String(64))
    trigger_type: Mapped[str] = mapped_column(String(32))
    trigger_source: Mapped[str | None] = mapped_column(String(128))
    scope_key: Mapped[str] = mapped_column(String(128))
    dedup_key: Mapped[str] = mapped_column(String(256))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(256))
    orchestration_rule_version: Mapped[str] = mapped_column(String(32))


class Benchmark(Base):
    __tablename__ = "benchmarks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    level: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(128))
    symbol: Mapped[str] = mapped_column(String(32))
    sector: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkDailyPrice(Base):
    __tablename__ = "benchmark_daily_prices"
    __table_args__ = (UniqueConstraint("benchmark_id", "trade_date", name="uq_benchmark_price_benchmark_date"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    benchmark_id: Mapped[int] = mapped_column(ForeignKey("benchmarks.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    source: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkRelativeAssessment(Base):
    __tablename__ = "benchmark_relative_assessments"
    __table_args__ = (
        UniqueConstraint(
            "prediction_id", "benchmark_level", "evaluated_at", name="uq_benchmark_relative_prediction_level_evaluated_at",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    benchmark_level: Mapped[str] = mapped_column(String(16))
    benchmark_id: Mapped[int | None] = mapped_column(ForeignKey("benchmarks.id"))
    benchmark_code: Mapped[str | None] = mapped_column(String(64))
    stock_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    benchmark_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    relative_alpha: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assessment_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkPerformanceReport(Base):
    __tablename__ = "benchmark_performance_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    benchmark_relative_environment: Mapped[str] = mapped_column(String(32), index=True)
    benchmark_level: Mapped[str] = mapped_column(String(16))
    window_label: Mapped[str] = mapped_column(String(128))
    segment_sample_count: Mapped[int] = mapped_column(Integer)
    segment_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    baseline_sample_count: Mapped[int] = mapped_column(Integer)
    baseline_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionOutcomeEvent(Base):
    __tablename__ = "prediction_outcome_events"
    __table_args__ = (
        Index("ix_prediction_outcome_events_prediction_id", "prediction_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    state: Mapped[str] = mapped_column(String(32))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    provider: Mapped[str | None] = mapped_column(String(64))
    prediction_version: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict] = mapped_column(JSON)
    monitor_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioCorrelationReport(Base):
    __tablename__ = "portfolio_correlation_reports"
    __table_args__ = (UniqueConstraint("scan_id", "evaluated_at", name="uq_portfolio_correlation_scan_evaluated_at"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    candidate_count: Mapped[int] = mapped_column(Integer)
    lookback_days: Mapped[int] = mapped_column(Integer)
    sector_concentration: Mapped[dict] = mapped_column(JSON)
    high_correlation_pairs: Mapped[list] = mapped_column(JSON)
    near_duplicate_stock_ids: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    correlation_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioUtilityAssessment(Base):
    __tablename__ = "portfolio_utility_assessments"
    __table_args__ = (UniqueConstraint("prediction_id", "evaluated_at", name="uq_portfolio_utility_prediction_evaluated_at"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    scan_id: Mapped[int] = mapped_column(ForeignKey("daily_candidate_scans.id"))
    sector: Mapped[str | None] = mapped_column(String(128))
    base_utility: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    concentration_penalty: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    correlation_penalty: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    preference_penalty: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    adjusted_utility: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    included: Mapped[bool] = mapped_column(Boolean)
    penalty_reasons: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    utility_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioSelectionEffectivenessReport(Base):
    __tablename__ = "portfolio_selection_effectiveness_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    window_label: Mapped[str] = mapped_column(String(128))
    top_k: Mapped[int] = mapped_column(Integer)
    diversified_sample_count: Mapped[int] = mapped_column(Integer)
    diversified_success_count: Mapped[int] = mapped_column(Integer)
    diversified_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    raw_sample_count: Mapped[int] = mapped_column(Integer)
    raw_success_count: Mapped[int] = mapped_column(Integer)
    raw_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    success_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effectiveness_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketCalendarVersion(Base):
    __tablename__ = "market_calendar_versions"
    __table_args__ = (
        UniqueConstraint("exchange", "version_label", name="uq_market_calendar_exchange_version_label"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    version_label: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64))
    timezone_name: Mapped[str] = mapped_column(String(64))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calendar_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketHoliday(Base):
    __tablename__ = "market_holidays"
    __table_args__ = (
        UniqueConstraint("calendar_version_id", "holiday_date", name="uq_market_holiday_version_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    calendar_version_id: Mapped[int] = mapped_column(ForeignKey("market_calendar_versions.id"), index=True)
    holiday_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketSpecialSession(Base):
    __tablename__ = "market_special_sessions"
    __table_args__ = (
        UniqueConstraint("calendar_version_id", "session_date", name="uq_market_special_session_version_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    calendar_version_id: Mapped[int] = mapped_column(ForeignKey("market_calendar_versions.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date)
    pre_market_start: Mapped[time | None] = mapped_column(Time)
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)
    post_market_end: Mapped[time | None] = mapped_column(Time)
    description: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketUnexpectedClosure(Base):
    __tablename__ = "market_unexpected_closures"
    __table_args__ = (
        UniqueConstraint("exchange", "closure_date", name="uq_market_unexpected_closure_exchange_date"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    closure_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(256))
    source: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InformationLatencyAssessment(Base):
    __tablename__ = "information_latency_assessments"
    __table_args__ = (UniqueConstraint("prediction_id", "evaluated_at", name="uq_information_latency_prediction_evaluated_at"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    horizon_days: Mapped[int] = mapped_column(Integer)
    sla_multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    category_latency_seconds: Mapped[dict] = mapped_column(JSON)
    sla_violations: Mapped[list] = mapped_column(JSON)
    suppress_eligibility: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latency_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LatencyDegradationReport(Base):
    __tablename__ = "latency_degradation_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    data_type: Mapped[str] = mapped_column(String(32))
    window_label: Mapped[str] = mapped_column(String(128))
    sample_count: Mapped[int] = mapped_column(Integer)
    average_latency_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    baseline_sample_count: Mapped[int] = mapped_column(Integer)
    baseline_average_latency_seconds: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    degradation_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShadowChallengerAssessment(Base):
    __tablename__ = "shadow_challenger_assessments"
    __table_args__ = (
        UniqueConstraint("champion_prediction_id", "challenger_model_version", name="uq_shadow_prediction_challenger"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    champion_prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    champion_model_version: Mapped[str] = mapped_column(String(64))
    challenger_model_version: Mapped[str] = mapped_column(String(64))
    challenger_predicted_probability: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    challenger_confidence: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shadow_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShadowChallengerComparisonReport(Base):
    __tablename__ = "shadow_challenger_comparison_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    challenger_model_version: Mapped[str] = mapped_column(String(64))
    champion_model_version: Mapped[str] = mapped_column(String(64))
    window_label: Mapped[str] = mapped_column(String(128))
    sample_count: Mapped[int] = mapped_column(Integer)
    champion_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    challenger_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    success_rate_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    champion_calibration_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    challenger_calibration_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    by_horizon: Mapped[list] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    comparison_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChampionRollback(Base):
    __tablename__ = "champion_rollbacks"
    __table_args__ = (
        UniqueConstraint("rolled_back_model_version", "restored_model_version", name="uq_rollback_from_to"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    rolled_back_model_version: Mapped[str] = mapped_column(String(64))
    restored_model_version: Mapped[str] = mapped_column(String(64))
    triggering_model_regression_check_id: Mapped[int | None] = mapped_column(ForeignKey("model_regression_checks.id"))
    resulting_model_promotion_id: Mapped[int] = mapped_column(ForeignKey("model_promotions.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approver: Mapped[str] = mapped_column(String(128))
    rollback_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResolvedFact(Base):
    __tablename__ = "resolved_facts"
    __table_args__ = (
        UniqueConstraint(
            "fact_type", "stock_id", "fact_key", "resolved_at", name="uq_resolved_fact_type_stock_key_resolved_at",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    fact_type: Mapped[str] = mapped_column(String(32), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    fact_key: Mapped[str] = mapped_column(String(128))
    resolved_value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    resolved_value_text: Mapped[str | None] = mapped_column(String(512))
    winning_source: Mapped[str | None] = mapped_column(String(64))
    winning_source_authority_tier: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    source_count: Mapped[int] = mapped_column(Integer)
    sources_considered: Mapped[list] = mapped_column(JSON)
    conflicting: Mapped[bool] = mapped_column(Boolean)
    resolution_reason: Mapped[str] = mapped_column(String(48))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolution_rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MicrostructureSnapshot(Base):
    __tablename__ = "microstructure_snapshots"
    __table_args__ = (UniqueConstraint("prediction_id", name="uq_microstructure_snapshot_prediction"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    liquidity_bucket: Mapped[str] = mapped_column(String(32))
    previous_liquidity_bucket: Mapped[str | None] = mapped_column(String(32))
    liquidity_regime_changed: Mapped[bool] = mapped_column(Boolean)
    average_daily_turnover: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    gap_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    gap_bucket: Mapped[str] = mapped_column(String(32))
    probable_circuit_band_event: Mapped[bool] = mapped_column(Boolean)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

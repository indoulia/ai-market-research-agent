/// EPIC-M3.8 — domain model parsed from the API's `ActivePrediction` JSON
/// shape (`GET /predictions/active[/{predictionId}]`,
/// `api/schemas/predictions_active.py`). Numeric fields arrive as decimal
/// strings (server-side `Decimal`) and are parsed here once, matching the
/// existing `Recommendation`/`TrackedPrediction` convention.
library;

/// Status values, mirrored verbatim from `app.prediction_outcome_monitor`
/// (EPIC-M1.119) -- the API never invents its own vocabulary for this
/// field, and neither does this app (AC: "active state is sourced from
/// M1.119, not recomputed differently in Flutter").
class ActivePredictionStatus {
  static const active = 'ACTIVE';
  static const targetHit = 'TARGET_HIT';
  static const stopLossHit = 'STOP_LOSS_HIT';
  static const horizonExpired = 'HORIZON_EXPIRED';
  static const invalidated = 'INVALIDATED';
  static const dataUnresolved = 'DATA_UNRESOLVED';

  static const terminal = {targetHit, stopLossHit, horizonExpired, invalidated};

  const ActivePredictionStatus._();
}

class ActivePrediction {
  final int predictionId;
  final String symbol;
  final String? companyName;
  final String exchange;
  final double? price;
  final double targetPrice;
  final double stopLoss;
  final int horizon;
  final int? remainingTradingDays;
  final double? distanceToTargetPercent;
  final double? distanceToStopLossPercent;
  final double? score;
  final double confidence;
  final double? trustScore;
  final String status;
  final DateTime? lastPriceAt;
  final DateTime? lastRevisionAt;
  final DateTime? nextEvaluationAt;

  const ActivePrediction({
    required this.predictionId,
    required this.symbol,
    required this.companyName,
    required this.exchange,
    required this.price,
    required this.targetPrice,
    required this.stopLoss,
    required this.horizon,
    required this.remainingTradingDays,
    required this.distanceToTargetPercent,
    required this.distanceToStopLossPercent,
    required this.score,
    required this.confidence,
    required this.trustScore,
    required this.status,
    required this.lastPriceAt,
    required this.lastRevisionAt,
    required this.nextEvaluationAt,
  });

  /// Where [price] sits between [stopLoss] (0.0) and [targetPrice] (1.0),
  /// clamped to `[0, 1]` for rendering a compact progress bar. Falls back
  /// to 0 when there is no current price yet or the target/stop-loss span
  /// is degenerate (never divides by zero).
  double get progressFraction {
    final p = price;
    final span = targetPrice - stopLoss;
    if (p == null || span <= 0) return 0;
    return ((p - stopLoss) / span).clamp(0.0, 1.0);
  }

  bool get isTerminal => ActivePredictionStatus.terminal.contains(status);

  static double? _parseNullableDecimal(dynamic value) {
    if (value == null) return null;
    return double.parse(value as String);
  }

  static double _parseDecimal(dynamic value) => double.parse(value as String);

  static DateTime? _parseNullableDateTime(dynamic value) {
    if (value == null) return null;
    return DateTime.parse(value as String);
  }

  factory ActivePrediction.fromJson(Map<String, dynamic> json) {
    return ActivePrediction(
      predictionId: json['predictionId'] as int,
      symbol: json['symbol'] as String,
      companyName: json['companyName'] as String?,
      exchange: json['exchange'] as String,
      price: _parseNullableDecimal(json['price']),
      targetPrice: _parseDecimal(json['targetPrice']),
      stopLoss: _parseDecimal(json['stopLoss']),
      horizon: json['horizon'] as int,
      remainingTradingDays: json['remainingTradingDays'] as int?,
      distanceToTargetPercent: _parseNullableDecimal(
        json['distanceToTargetPercent'],
      ),
      distanceToStopLossPercent: _parseNullableDecimal(
        json['distanceToStopLossPercent'],
      ),
      score: _parseNullableDecimal(json['score']),
      confidence: _parseDecimal(json['confidence']),
      trustScore: _parseNullableDecimal(json['trustScore']),
      status: json['status'] as String,
      lastPriceAt: _parseNullableDateTime(json['lastPriceAt']),
      lastRevisionAt: _parseNullableDateTime(json['lastRevisionAt']),
      nextEvaluationAt: _parseNullableDateTime(json['nextEvaluationAt']),
    );
  }
}

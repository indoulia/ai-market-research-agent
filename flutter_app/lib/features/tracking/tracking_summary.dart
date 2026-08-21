/// EPIC-M1.148 — domain model parsed from EPIC-M1.147's real, merged
/// `TrackingSummary` shape (`api/schemas/tracking.py`). Numeric fields
/// arrive as decimal strings and are parsed here once.
class TrackingSummary {
  final String range;
  final int predictionCount;
  final int closedCount;
  final double? targetHitRate;
  final double? stopLossRate;
  final double? horizonExpiryRate;
  final double? avgRealizedReturn;
  final double? avgPredictedReturn;
  final double? calibrationScore;
  final double? trustScore;
  final double? trustDelta;
  final String? modelVersion;
  final double? benchmarkReturn;
  final double? relativeReturn;
  final bool smallSample;

  const TrackingSummary({
    required this.range,
    required this.predictionCount,
    required this.closedCount,
    required this.targetHitRate,
    required this.stopLossRate,
    required this.horizonExpiryRate,
    required this.avgRealizedReturn,
    required this.avgPredictedReturn,
    required this.calibrationScore,
    required this.trustScore,
    required this.trustDelta,
    required this.modelVersion,
    required this.benchmarkReturn,
    required this.relativeReturn,
    required this.smallSample,
  });

  /// Predictions still awaiting an outcome — not a server-reported field,
  /// just [predictionCount] minus [closedCount] (the Layout's "active" KPI).
  int get activeCount => predictionCount - closedCount;

  static double? _parseNullableDecimal(dynamic value) {
    if (value == null) return null;
    return double.parse(value as String);
  }

  factory TrackingSummary.fromJson(Map<String, dynamic> json) {
    return TrackingSummary(
      range: json['range'] as String,
      predictionCount: json['predictionCount'] as int,
      closedCount: json['closedCount'] as int,
      targetHitRate: _parseNullableDecimal(json['targetHitRate']),
      stopLossRate: _parseNullableDecimal(json['stopLossRate']),
      horizonExpiryRate: _parseNullableDecimal(json['horizonExpiryRate']),
      avgRealizedReturn: _parseNullableDecimal(json['avgRealizedReturn']),
      avgPredictedReturn: _parseNullableDecimal(json['avgPredictedReturn']),
      calibrationScore: _parseNullableDecimal(json['calibrationScore']),
      trustScore: _parseNullableDecimal(json['trustScore']),
      trustDelta: _parseNullableDecimal(json['trustDelta']),
      modelVersion: json['modelVersion'] as String?,
      benchmarkReturn: _parseNullableDecimal(json['benchmarkReturn']),
      relativeReturn: _parseNullableDecimal(json['relativeReturn']),
      smallSample: json['smallSample'] as bool,
    );
  }
}

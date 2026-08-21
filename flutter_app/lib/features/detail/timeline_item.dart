/// EPIC-M3.4 — one entry from `GET /recommendations/{id}/timeline`: the
/// full, ordered prediction-version timeline (the original prediction as
/// version 1, plus every immutable revision). Never mutated or re-derived
/// client-side — matches the immutability convention already established
/// by [RecommendationHistoryItem] (EPIC-M1.137/138).
class RecommendationTimelineItem {
  final int version;
  final DateTime timestamp;
  final String reason;
  final String changeSummary;
  final List<String> affectedMetrics;
  final double price;
  final double targetPrice;
  final double stopLoss;
  final double probability;
  final double? score;
  final double confidence;
  final double? trustScore;

  const RecommendationTimelineItem({
    required this.version,
    required this.timestamp,
    required this.reason,
    required this.changeSummary,
    required this.affectedMetrics,
    required this.price,
    required this.targetPrice,
    required this.stopLoss,
    required this.probability,
    required this.score,
    required this.confidence,
    required this.trustScore,
  });

  /// `true` for the original prediction (never a revision) — mirrors the
  /// API's `TIMELINE_REASON_INITIAL_PREDICTION` constant
  /// (`api/schemas/recommendation_detail.py`).
  bool get isInitial => reason == 'INITIAL_PREDICTION';

  static double? _decimalOrNull(dynamic v) =>
      v == null ? null : double.parse(v as String);
  static double _decimal(dynamic v) => double.parse(v as String);

  factory RecommendationTimelineItem.fromJson(Map<String, dynamic> json) {
    return RecommendationTimelineItem(
      version: json['version'] as int,
      timestamp: DateTime.parse(json['timestamp'] as String),
      reason: json['reason'] as String,
      changeSummary: json['changeSummary'] as String,
      affectedMetrics: (json['affectedMetrics'] as List).cast<String>(),
      price: _decimal(json['price']),
      targetPrice: _decimal(json['targetPrice']),
      stopLoss: _decimal(json['stopLoss']),
      probability: _decimal(json['probability']),
      score: _decimalOrNull(json['score']),
      confidence: _decimal(json['confidence']),
      trustScore: _decimalOrNull(json['trustScore']),
    );
  }
}

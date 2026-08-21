/// EPIC-M1.138 — one immutable revision/tracking snapshot from
/// EPIC-M1.137's `GET /recommendations/{id}/history`. Never mutated or
/// re-derived client-side (M1.137 AC: "historical versions are immutable").
class RecommendationHistoryItem {
  final DateTime timestamp;
  final int version;
  final double price;
  final double targetPrice;
  final double stopLoss;
  final double probability;
  final double? score;
  final double confidence;
  final double? trustScore;
  final String triggerType;
  final int? triggerEventId;
  final String changeSummary;

  const RecommendationHistoryItem({
    required this.timestamp,
    required this.version,
    required this.price,
    required this.targetPrice,
    required this.stopLoss,
    required this.probability,
    required this.score,
    required this.confidence,
    required this.trustScore,
    required this.triggerType,
    required this.triggerEventId,
    required this.changeSummary,
  });

  static double? _decimalOrNull(dynamic v) =>
      v == null ? null : double.parse(v as String);
  static double _decimal(dynamic v) => double.parse(v as String);

  factory RecommendationHistoryItem.fromJson(Map<String, dynamic> json) {
    return RecommendationHistoryItem(
      timestamp: DateTime.parse(json['timestamp'] as String),
      version: json['version'] as int,
      price: _decimal(json['price']),
      targetPrice: _decimal(json['targetPrice']),
      stopLoss: _decimal(json['stopLoss']),
      probability: _decimal(json['probability']),
      score: _decimalOrNull(json['score']),
      confidence: _decimal(json['confidence']),
      trustScore: _decimalOrNull(json['trustScore']),
      triggerType: json['triggerType'] as String,
      triggerEventId: json['triggerEventId'] as int?,
      changeSummary: json['changeSummary'] as String,
    );
  }
}

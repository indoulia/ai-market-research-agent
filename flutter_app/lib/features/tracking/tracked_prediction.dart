/// EPIC-M1.148 — parsed from EPIC-M1.147's `TrackedPrediction`
/// (`api/schemas/tracking.py`). [id] is deliberately the same
/// `RecommendationGeneration.id` space `RecommendationDetailScreen`
/// expects (confirmed against `api/services/tracking.py`'s
/// `list_tracked_predictions` — not guessed), so drill-down navigation
/// to `/recommendation/:id` is safe.
class TrackedPrediction {
  final int id;
  final String symbol;
  final String status;
  final DateTime asOf;
  final int horizonDays;
  final double predictedReturn;
  final double? realizedReturn;
  final String? outcome;
  final String modelVersion;

  const TrackedPrediction({
    required this.id,
    required this.symbol,
    required this.status,
    required this.asOf,
    required this.horizonDays,
    required this.predictedReturn,
    required this.realizedReturn,
    required this.outcome,
    required this.modelVersion,
  });

  factory TrackedPrediction.fromJson(Map<String, dynamic> json) {
    return TrackedPrediction(
      id: json['id'] as int,
      symbol: json['symbol'] as String,
      status: json['status'] as String,
      asOf: DateTime.parse(json['asOf'] as String),
      horizonDays: json['horizonDays'] as int,
      predictedReturn: double.parse(json['predictedReturn'] as String),
      realizedReturn: json['realizedReturn'] == null
          ? null
          : double.parse(json['realizedReturn'] as String),
      outcome: json['outcome'] as String?,
      modelVersion: json['modelVersion'] as String,
    );
  }
}

/// EPIC-M1.136 — domain model parsed from EPIC-M1.135's `RecommendationSummary`
/// JSON shape (`docs/api/openapi.json`). Numeric fields arrive as decimal
/// strings (server-side `Decimal`, serialized as string for precision) and
/// are parsed here once rather than in every screen.
class Recommendation {
  final int id;
  final String symbol;
  final String exchange;
  final String? companyName;
  final DateTime asOf;
  final double? price;
  final double? changePct;
  final String recommendationLabel;
  final int horizonDays;
  final double targetPrice;
  final double stopLoss;
  final double upsidePct;
  final double probability;
  final double score;
  final double confidence;
  final double? trustScore;
  final String? uncertaintyLevel;
  final String? fundamentalSummary;
  final String? newsSummary;
  final String? eventSummary;
  final String? marketSummary;
  final String evidenceFreshness;
  final String status;
  final DateTime updatedAt;

  const Recommendation({
    required this.id,
    required this.symbol,
    required this.exchange,
    required this.companyName,
    required this.asOf,
    required this.price,
    required this.changePct,
    required this.recommendationLabel,
    required this.horizonDays,
    required this.targetPrice,
    required this.stopLoss,
    required this.upsidePct,
    required this.probability,
    required this.score,
    required this.confidence,
    required this.trustScore,
    required this.uncertaintyLevel,
    required this.fundamentalSummary,
    required this.newsSummary,
    required this.eventSummary,
    required this.marketSummary,
    required this.evidenceFreshness,
    required this.status,
    required this.updatedAt,
  });

  static double? _parseNullableDecimal(dynamic value) {
    if (value == null) return null;
    return double.parse(value as String);
  }

  static double _parseDecimal(dynamic value) => double.parse(value as String);

  factory Recommendation.fromJson(Map<String, dynamic> json) {
    return Recommendation(
      id: json['id'] as int,
      symbol: json['symbol'] as String,
      exchange: json['exchange'] as String,
      companyName: json['companyName'] as String?,
      asOf: DateTime.parse(json['asOf'] as String),
      price: _parseNullableDecimal(json['price']),
      changePct: _parseNullableDecimal(json['changePct']),
      recommendationLabel: json['recommendation'] as String,
      horizonDays: json['horizonDays'] as int,
      targetPrice: _parseDecimal(json['targetPrice']),
      stopLoss: _parseDecimal(json['stopLoss']),
      upsidePct: _parseDecimal(json['upsidePct']),
      probability: _parseDecimal(json['probability']),
      score: _parseDecimal(json['score']),
      confidence: _parseDecimal(json['confidence']),
      trustScore: _parseNullableDecimal(json['trustScore']),
      uncertaintyLevel: json['uncertaintyLevel'] as String?,
      fundamentalSummary: json['fundamentalSummary'] as String?,
      newsSummary: json['newsSummary'] as String?,
      eventSummary: json['eventSummary'] as String?,
      marketSummary: json['marketSummary'] as String?,
      evidenceFreshness: json['evidenceFreshness'] as String,
      status: json['status'] as String,
      updatedAt: DateTime.parse(json['updatedAt'] as String),
    );
  }
}

/// EPIC-M1.138 — domain model parsed from EPIC-M1.137's `RecommendationDetail`
/// JSON shape (`docs/api/openapi.json`). Mirrors `Recommendation` (M1.136)'s
/// decimal-as-string parsing convention.
class RecommendationDetail {
  final int id;
  final String symbol;
  final String exchange;
  final String? companyName;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime asOf;
  final double entryPrice;
  final double? currentPrice;
  final double targetPrice;
  final double stopLoss;
  final int horizonDays;
  final DateTime? expiryAt;
  final double upsidePct;
  final double probability;
  final double? score;
  final double confidence;
  final double? trustScore;
  final String? uncertainty;
  final String? evidenceStrength;
  final String? fundamental;
  final String? technical;
  final String? market;
  final String? news;
  final String? events;

  /// Always null until EPIC-M1.129 (benchmark-relative alpha) exists —
  /// rendered as an honest "not available yet", never fabricated.
  final String? benchmarkRelative;
  final String liquidity;
  final List<String> providerEvidence;
  final String status;

  /// Opaque version-tag bundle (model/feature/consensus/etc.) — passed
  /// through unparsed to EPIC-M1.141's feedback submission, which must
  /// reference "the exact recommendation version visible to the user"
  /// (M1.142 AC) without this UI needing to interpret its internals.
  final Map<String, dynamic> predictionVersion;

  const RecommendationDetail({
    required this.id,
    required this.symbol,
    required this.exchange,
    required this.companyName,
    required this.createdAt,
    required this.updatedAt,
    required this.asOf,
    required this.entryPrice,
    required this.currentPrice,
    required this.targetPrice,
    required this.stopLoss,
    required this.horizonDays,
    required this.expiryAt,
    required this.upsidePct,
    required this.probability,
    required this.score,
    required this.confidence,
    required this.trustScore,
    required this.uncertainty,
    required this.evidenceStrength,
    required this.fundamental,
    required this.technical,
    required this.market,
    required this.news,
    required this.events,
    required this.benchmarkRelative,
    required this.liquidity,
    required this.providerEvidence,
    required this.status,
    required this.predictionVersion,
  });

  static double? _decimalOrNull(dynamic v) =>
      v == null ? null : double.parse(v as String);
  static double _decimal(dynamic v) => double.parse(v as String);

  factory RecommendationDetail.fromJson(Map<String, dynamic> json) {
    return RecommendationDetail(
      id: json['id'] as int,
      symbol: json['symbol'] as String,
      exchange: json['exchange'] as String,
      companyName: json['companyName'] as String?,
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
      asOf: DateTime.parse(json['asOf'] as String),
      entryPrice: _decimal(json['entryPrice']),
      currentPrice: _decimalOrNull(json['currentPrice']),
      targetPrice: _decimal(json['targetPrice']),
      stopLoss: _decimal(json['stopLoss']),
      horizonDays: json['horizonDays'] as int,
      expiryAt: json['expiryAt'] == null
          ? null
          : DateTime.parse(json['expiryAt'] as String),
      upsidePct: _decimal(json['upsidePct']),
      probability: _decimal(json['probability']),
      score: _decimalOrNull(json['score']),
      confidence: _decimal(json['confidence']),
      trustScore: _decimalOrNull(json['trustScore']),
      uncertainty: json['uncertainty'] as String?,
      evidenceStrength: json['evidenceStrength'] as String?,
      fundamental: json['fundamental'] as String?,
      technical: json['technical'] as String?,
      market: json['market'] as String?,
      news: json['news'] as String?,
      events: json['events'] as String?,
      benchmarkRelative: json['benchmarkRelative'] as String?,
      liquidity: json['liquidity'] as String,
      providerEvidence: (json['providerEvidence'] as List).cast<String>(),
      status: json['status'] as String,
      predictionVersion: json['predictionVersion'] as Map<String, dynamic>,
    );
  }
}

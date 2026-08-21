/// EPIC-M1.140 — parsed from EPIC-M1.139's `GET /api/v1/events`
/// (corporate actions). Named `MarketEventItem` to avoid confusion with
/// EPIC-M1.138's per-recommendation `RecommendationEventItem`.
class MarketEventItem {
  final String symbol;
  final String type;
  final String title;
  final DateTime effectiveAt;
  final DateTime detectedAt;
  final String? materiality;
  final String source;
  final int evidenceId;

  const MarketEventItem({
    required this.symbol,
    required this.type,
    required this.title,
    required this.effectiveAt,
    required this.detectedAt,
    required this.materiality,
    required this.source,
    required this.evidenceId,
  });

  factory MarketEventItem.fromJson(Map<String, dynamic> json) {
    return MarketEventItem(
      symbol: json['symbol'] as String,
      type: json['type'] as String,
      title: json['title'] as String,
      effectiveAt: DateTime.parse(json['effectiveAt'] as String),
      detectedAt: DateTime.parse(json['detectedAt'] as String),
      materiality: json['materiality'] as String?,
      source: json['source'] as String,
      evidenceId: json['evidenceId'] as int,
    );
  }
}

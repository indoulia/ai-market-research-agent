/// EPIC-M1.140 — parsed from EPIC-M1.139's `GET /api/v1/news`.
class NewsItem {
  final String symbol;
  final String headline;
  final String source;
  final DateTime publishedAt;
  final DateTime detectedAt;
  final String materiality;
  final List<String> affectedSecurities;
  final int evidenceId;

  const NewsItem({
    required this.symbol,
    required this.headline,
    required this.source,
    required this.publishedAt,
    required this.detectedAt,
    required this.materiality,
    required this.affectedSecurities,
    required this.evidenceId,
  });

  factory NewsItem.fromJson(Map<String, dynamic> json) {
    return NewsItem(
      symbol: json['symbol'] as String,
      headline: json['headline'] as String,
      source: json['source'] as String,
      publishedAt: DateTime.parse(json['publishedAt'] as String),
      detectedAt: DateTime.parse(json['detectedAt'] as String),
      materiality: json['materiality'] as String,
      affectedSecurities: (json['affectedSecurities'] as List).cast<String>(),
      evidenceId: json['evidenceId'] as int,
    );
  }
}

/// EPIC-M1.140 — parsed from EPIC-M1.139's `GET /api/v1/news`.
/// EPIC-M3.5 added [eventType] (news-vs-corporate-event classification the
/// API always had, just not previously threaded to the Flutter client).
class NewsItem {
  final String symbol;
  final String headline;
  final String source;
  final DateTime publishedAt;
  final DateTime detectedAt;
  final String materiality;
  final String eventType;
  final List<String> affectedSecurities;
  final int evidenceId;

  const NewsItem({
    required this.symbol,
    required this.headline,
    required this.source,
    required this.publishedAt,
    required this.detectedAt,
    required this.materiality,
    required this.eventType,
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
      eventType: json['eventType'] as String? ?? 'NEWS_STORY',
      affectedSecurities: (json['affectedSecurities'] as List).cast<String>(),
      evidenceId: json['evidenceId'] as int,
    );
  }
}

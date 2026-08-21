/// EPIC-M3.6 — one entry from `GET /api/v1/discovery/candidates`. Replaces
/// EPIC-M1.139's `/discoveries` as this screen's data source: same
/// discovery universe, reprojected with an explicit `lifecycleStage`
/// (discovered/qualified/suppressed/published) and, only for a signed-in
/// caller, a `suppressionReason` -- never fabricated when absent.
class DiscoveryItem {
  final int candidateId;
  final String symbol;
  final String? companyName;
  final String exchange;
  final String sector;
  final String industry;
  final String marketCapBucket;
  final String liquidity;
  final DateTime discoveredAt;
  final List<String> discoverySources;
  final List<String> discoveryReasons;
  final double? score;
  final double? trustScore;
  final String lifecycleStage;
  final String? suppressionReason;
  final int? publishedRecommendationId;

  const DiscoveryItem({
    required this.candidateId,
    required this.symbol,
    required this.companyName,
    required this.exchange,
    required this.sector,
    required this.industry,
    required this.marketCapBucket,
    required this.liquidity,
    required this.discoveredAt,
    required this.discoverySources,
    required this.discoveryReasons,
    required this.score,
    required this.trustScore,
    required this.lifecycleStage,
    required this.suppressionReason,
    required this.publishedRecommendationId,
  });

  static double? _decimalOrNull(dynamic v) =>
      v == null ? null : double.parse(v as String);

  factory DiscoveryItem.fromJson(Map<String, dynamic> json) {
    return DiscoveryItem(
      candidateId: json['candidateId'] as int,
      symbol: json['symbol'] as String,
      companyName: json['companyName'] as String?,
      exchange: json['exchange'] as String,
      sector: json['sector'] as String,
      industry: json['industry'] as String,
      marketCapBucket: json['marketCapBucket'] as String,
      liquidity: json['liquidity'] as String,
      discoveredAt: DateTime.parse(json['discoveredAt'] as String),
      discoverySources: (json['discoverySources'] as List).cast<String>(),
      discoveryReasons: (json['discoveryReasons'] as List).cast<String>(),
      score: _decimalOrNull(json['score']),
      trustScore: _decimalOrNull(json['trustScore']),
      lifecycleStage: json['lifecycleStage'] as String,
      suppressionReason: json['suppressionReason'] as String?,
      publishedRecommendationId: json['publishedRecommendationId'] as int?,
    );
  }
}

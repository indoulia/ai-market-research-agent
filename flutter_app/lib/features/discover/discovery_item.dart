/// EPIC-M1.140 — one entry from EPIC-M1.139's `GET /api/v1/discoveries`.
/// `status`/`score`/`trustScore` are honestly null/`PENDING_ANALYSIS` for a
/// discovered candidate that was never routed through the real pipeline —
/// never fabricated.
class DiscoveryItem {
  final String symbol;
  final String? companyName;
  final String exchange;
  final String sector;
  final String industry;
  final String marketCapBucket;
  final String liquidity;
  final DateTime discoveredAt;
  final List<String> discoveryReasons;
  final double? score;
  final double? trustScore;
  final bool? eligibility;
  final String status;

  const DiscoveryItem({
    required this.symbol,
    required this.companyName,
    required this.exchange,
    required this.sector,
    required this.industry,
    required this.marketCapBucket,
    required this.liquidity,
    required this.discoveredAt,
    required this.discoveryReasons,
    required this.score,
    required this.trustScore,
    required this.eligibility,
    required this.status,
  });

  static double? _decimalOrNull(dynamic v) =>
      v == null ? null : double.parse(v as String);

  factory DiscoveryItem.fromJson(Map<String, dynamic> json) {
    return DiscoveryItem(
      symbol: json['symbol'] as String,
      companyName: json['companyName'] as String?,
      exchange: json['exchange'] as String,
      sector: json['sector'] as String,
      industry: json['industry'] as String,
      marketCapBucket: json['marketCapBucket'] as String,
      liquidity: json['liquidity'] as String,
      discoveredAt: DateTime.parse(json['discoveredAt'] as String),
      discoveryReasons: (json['discoveryReasons'] as List).cast<String>(),
      score: _decimalOrNull(json['score']),
      trustScore: _decimalOrNull(json['trustScore']),
      eligibility: json['eligibility'] as bool?,
      status: json['status'] as String,
    );
  }
}

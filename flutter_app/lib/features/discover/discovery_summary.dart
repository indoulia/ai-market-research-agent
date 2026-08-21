/// EPIC-M3.6 — `GET /api/v1/discovery/summary`: discovered/analyzed/
/// qualified/published funnel counts plus per-source discovery
/// effectiveness (reprojected from `app.discovery_effectiveness`, M1.28).
class DiscoveryFunnelCounts {
  final int discovered;
  final int analyzed;
  final int qualified;
  final int suppressed;
  final int published;

  const DiscoveryFunnelCounts({
    required this.discovered,
    required this.analyzed,
    required this.qualified,
    required this.suppressed,
    required this.published,
  });

  factory DiscoveryFunnelCounts.fromJson(Map<String, dynamic> json) {
    return DiscoveryFunnelCounts(
      discovered: json['discovered'] as int,
      analyzed: json['analyzed'] as int,
      qualified: json['qualified'] as int,
      suppressed: json['suppressed'] as int,
      published: json['published'] as int,
    );
  }
}

class DiscoverySourceEffectiveness {
  final String source;
  final int discoveredCount;
  final int qualifiedCount;
  final double? successRate;
  final String verdict;

  const DiscoverySourceEffectiveness({
    required this.source,
    required this.discoveredCount,
    required this.qualifiedCount,
    required this.successRate,
    required this.verdict,
  });

  factory DiscoverySourceEffectiveness.fromJson(Map<String, dynamic> json) {
    return DiscoverySourceEffectiveness(
      source: json['source'] as String,
      discoveredCount: json['discoveredCount'] as int,
      qualifiedCount: json['qualifiedCount'] as int,
      successRate: json['successRate'] == null
          ? null
          : double.parse(json['successRate'] as String),
      verdict: json['verdict'] as String,
    );
  }
}

class DiscoverySummary {
  final DiscoveryFunnelCounts counts;
  final List<DiscoverySourceEffectiveness> effectivenessBySource;

  const DiscoverySummary({
    required this.counts,
    required this.effectivenessBySource,
  });

  factory DiscoverySummary.fromJson(Map<String, dynamic> json) {
    return DiscoverySummary(
      counts: DiscoveryFunnelCounts.fromJson(
        json['counts'] as Map<String, dynamic>,
      ),
      effectivenessBySource: (json['effectivenessBySource'] as List)
          .cast<Map<String, dynamic>>()
          .map(DiscoverySourceEffectiveness.fromJson)
          .toList(),
    );
  }
}

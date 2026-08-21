/// EPIC-M3.6 — one day of `GET /api/v1/discovery/history`'s timeline,
/// oldest-first.
class DiscoveryHistoryPoint {
  final DateTime scanDate;
  final int discoveredCount;
  final int analyzedCount;
  final int qualifiedCount;
  final int suppressedCount;
  final int publishedCount;

  const DiscoveryHistoryPoint({
    required this.scanDate,
    required this.discoveredCount,
    required this.analyzedCount,
    required this.qualifiedCount,
    required this.suppressedCount,
    required this.publishedCount,
  });

  factory DiscoveryHistoryPoint.fromJson(Map<String, dynamic> json) {
    return DiscoveryHistoryPoint(
      scanDate: DateTime.parse(json['scanDate'] as String),
      discoveredCount: json['discoveredCount'] as int,
      analyzedCount: json['analyzedCount'] as int,
      qualifiedCount: json['qualifiedCount'] as int,
      suppressedCount: json['suppressedCount'] as int,
      publishedCount: json['publishedCount'] as int,
    );
  }
}

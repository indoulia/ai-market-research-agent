/// EPIC-M3.11 — one row of `GET /api/v1/system/data-freshness`
/// (`api/schemas/system.py::DataFreshnessItem`): the last successful fetch
/// and staleness, per capability, against M1.35's own `FRESHNESS_POLICY`
/// threshold.
class DataFreshnessItem {
  final String capability;
  final DateTime? lastSuccessAt;
  final int? ageSeconds;
  final int thresholdSeconds;
  final bool isFresh;

  const DataFreshnessItem({
    required this.capability,
    required this.lastSuccessAt,
    required this.ageSeconds,
    required this.thresholdSeconds,
    required this.isFresh,
  });

  factory DataFreshnessItem.fromJson(Map<String, dynamic> json) =>
      DataFreshnessItem(
        capability: json['capability'] as String,
        lastSuccessAt: json['lastSuccessAt'] == null
            ? null
            : DateTime.parse(json['lastSuccessAt'] as String),
        ageSeconds: json['ageSeconds'] as int?,
        thresholdSeconds: json['thresholdSeconds'] as int,
        isFresh: json['isFresh'] as bool,
      );
}

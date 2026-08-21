/// EPIC-M1.148 — parsed from EPIC-M1.147's `BreakdownResponse`/
/// `BreakdownItem` (`api/schemas/tracking.py`).
class TrackingBreakdownItem {
  final String key;
  final int predictionCount;
  final int closedCount;
  final double? targetHitRate;
  final double? avgRealizedReturn;
  final bool smallSample;

  const TrackingBreakdownItem({
    required this.key,
    required this.predictionCount,
    required this.closedCount,
    required this.targetHitRate,
    required this.avgRealizedReturn,
    required this.smallSample,
  });

  factory TrackingBreakdownItem.fromJson(Map<String, dynamic> json) {
    return TrackingBreakdownItem(
      key: json['key'] as String,
      predictionCount: json['predictionCount'] as int,
      closedCount: json['closedCount'] as int,
      targetHitRate: json['targetHitRate'] == null
          ? null
          : double.parse(json['targetHitRate'] as String),
      avgRealizedReturn: json['avgRealizedReturn'] == null
          ? null
          : double.parse(json['avgRealizedReturn'] as String),
      smallSample: json['smallSample'] as bool,
    );
  }
}

class TrackingBreakdown {
  final String dimension;
  final List<TrackingBreakdownItem> items;

  const TrackingBreakdown({required this.dimension, required this.items});

  factory TrackingBreakdown.fromJson(Map<String, dynamic> json) {
    return TrackingBreakdown(
      dimension: json['dimension'] as String,
      items: (json['items'] as List)
          .cast<Map<String, dynamic>>()
          .map(TrackingBreakdownItem.fromJson)
          .toList(),
    );
  }
}

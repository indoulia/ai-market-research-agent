/// EPIC-M1.148 — parsed from EPIC-M1.147's `TimeseriesResponse`/
/// `TimeseriesPoint` (`api/schemas/tracking.py`). A point's [value] is
/// `null` when a bucket had no evaluable predictions — an honest gap in
/// the series, not zero.
class TrackingTimeseriesPoint {
  final DateTime bucketStart;
  final double? value;
  final int sampleCount;

  const TrackingTimeseriesPoint({
    required this.bucketStart,
    required this.value,
    required this.sampleCount,
  });

  factory TrackingTimeseriesPoint.fromJson(Map<String, dynamic> json) {
    return TrackingTimeseriesPoint(
      bucketStart: DateTime.parse(json['bucketStart'] as String),
      value: json['value'] == null
          ? null
          : double.parse(json['value'] as String),
      sampleCount: json['sampleCount'] as int,
    );
  }
}

class TrackingTimeseries {
  final String metric;
  final String range;
  final String bucket;
  final List<TrackingTimeseriesPoint> points;

  const TrackingTimeseries({
    required this.metric,
    required this.range,
    required this.bucket,
    required this.points,
  });

  factory TrackingTimeseries.fromJson(Map<String, dynamic> json) {
    return TrackingTimeseries(
      metric: json['metric'] as String,
      range: json['range'] as String,
      bucket: json['bucket'] as String,
      points: (json['points'] as List)
          .cast<Map<String, dynamic>>()
          .map(TrackingTimeseriesPoint.fromJson)
          .toList(),
    );
  }
}

import '../../core/api_client.dart';
import 'tracked_prediction.dart';
import 'tracking_breakdown.dart';
import 'tracking_summary.dart';
import 'tracking_timeseries.dart';

/// EPIC-M1.148 — one cursor-paginated page of [TrackedPrediction]s
/// (`GET /tracking/predictions`), matching the `meta.nextCursor`
/// convention every other cursor-paginated endpoint in this app uses.
class TrackedPredictionsPage {
  final List<TrackedPrediction> items;
  final String? nextCursor;

  const TrackedPredictionsPage({required this.items, required this.nextCursor});
}

/// EPIC-M1.148 — repository boundary over EPIC-M1.147's real, merged
/// `/tracking/summary`, `/tracking/timeseries`, `/tracking/breakdown` and
/// `/tracking/predictions` contracts.
class TrackingRepository {
  final ApiClient _client;

  TrackingRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<TrackingSummary> fetchSummary({required String range}) async {
    final response = await _client.get(
      '/tracking/summary',
      query: {'range': range},
    );
    return TrackingSummary.fromJson(response.data as Map<String, dynamic>);
  }

  Future<TrackingTimeseries> fetchTimeseries({
    required String metric,
    required String range,
    required String bucket,
  }) async {
    final response = await _client.get(
      '/tracking/timeseries',
      query: {'metric': metric, 'range': range, 'bucket': bucket},
    );
    return TrackingTimeseries.fromJson(response.data as Map<String, dynamic>);
  }

  Future<TrackingBreakdown> fetchBreakdown({required String dimension}) async {
    final response = await _client.get(
      '/tracking/breakdown',
      query: {'dimension': dimension},
    );
    return TrackingBreakdown.fromJson(response.data as Map<String, dynamic>);
  }

  Future<TrackedPredictionsPage> fetchPredictions({
    required String status,
    String? cursor,
    int pageSize = 10,
  }) async {
    final response = await _client.get(
      '/tracking/predictions',
      query: {
        'status': status,
        'pageSize': pageSize.toString(),
        'cursor': ?cursor,
      },
    );
    final items = (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(TrackedPrediction.fromJson)
        .toList();
    return TrackedPredictionsPage(
      items: items,
      nextCursor: response.meta['nextCursor'] as String?,
    );
  }
}

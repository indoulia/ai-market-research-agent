import '../../core/api_client.dart';
import 'active_prediction.dart';
import 'tracked_prediction.dart';
import 'tracking_breakdown.dart';
import 'tracking_filters.dart';
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

/// EPIC-M3.8 — one cursor-paginated page of [ActivePrediction]s
/// (`GET /predictions/active`).
class ActivePredictionsPage {
  final List<ActivePrediction> items;
  final String? nextCursor;

  const ActivePredictionsPage({required this.items, required this.nextCursor});
}

/// EPIC-M1.148 — repository boundary over EPIC-M1.147's real, merged
/// `/tracking/summary`, `/tracking/timeseries`, `/tracking/breakdown` and
/// `/tracking/predictions` contracts.
class TrackingRepository {
  final ApiClient _client;

  TrackingRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<TrackingSummary> fetchSummary({
    required String range,
    TrackingFilters filters = const TrackingFilters(),
  }) async {
    final response = await _client.get(
      '/tracking/summary',
      query: {'range': range, ...filters.toQuery()},
    );
    return TrackingSummary.fromJson(response.data as Map<String, dynamic>);
  }

  Future<TrackingTimeseries> fetchTimeseries({
    required String metric,
    required String range,
    required String bucket,
    TrackingFilters filters = const TrackingFilters(),
  }) async {
    final response = await _client.get(
      '/tracking/timeseries',
      query: {
        'metric': metric,
        'range': range,
        'bucket': bucket,
        ...filters.toQuery(),
      },
    );
    return TrackingTimeseries.fromJson(response.data as Map<String, dynamic>);
  }

  Future<TrackingBreakdown> fetchBreakdown({
    required String dimension,
    TrackingFilters filters = const TrackingFilters(),
  }) async {
    final response = await _client.get(
      '/tracking/breakdown',
      query: {'dimension': dimension, ...filters.toQuery()},
    );
    return TrackingBreakdown.fromJson(response.data as Map<String, dynamic>);
  }

  Future<TrackedPredictionsPage> fetchPredictions({
    required String status,
    String? cursor,
    int pageSize = 10,
    TrackingFilters filters = const TrackingFilters(),
  }) async {
    final response = await _client.get(
      '/tracking/predictions',
      query: {
        'status': status,
        'pageSize': pageSize.toString(),
        'cursor': ?cursor,
        ...filters.toQuery(),
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

  /// EPIC-M3.8 — `GET /predictions/active`: the compact live-monitoring
  /// feed (current price/target/SL distances, horizon remaining, Trust,
  /// M1.119-sourced status). Distinct from [fetchPredictions] above
  /// (EPIC-M1.147's historical predicted-vs-realized track record).
  Future<ActivePredictionsPage> fetchActivePredictions({
    String? cursor,
    int pageSize = 10,
  }) async {
    final response = await _client.get(
      '/predictions/active',
      query: {'pageSize': pageSize.toString(), 'cursor': ?cursor},
    );
    final items = (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(ActivePrediction.fromJson)
        .toList();
    return ActivePredictionsPage(
      items: items,
      nextCursor: response.meta['nextCursor'] as String?,
    );
  }

  /// EPIC-M3.8 — `GET /predictions/active/{predictionId}`: a fresh, single
  /// re-fetch for the detail view (drill-down from the live feed always
  /// re-reads server freshness rather than reusing the list's snapshot).
  Future<ActivePrediction> fetchActivePrediction(int predictionId) async {
    final response = await _client.get('/predictions/active/$predictionId');
    return ActivePrediction.fromJson(response.data as Map<String, dynamic>);
  }
}

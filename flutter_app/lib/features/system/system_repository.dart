import '../../core/api_client.dart';
import 'data_freshness_item.dart';
import 'provider_status.dart';
import 'system_event.dart';
import 'system_health_summary.dart';

/// EPIC-M3.11 — one page of `GET /api/v1/system/events`.
class SystemEventsPage {
  final List<SystemEvent> items;
  final String? nextCursor;
  const SystemEventsPage({required this.items, required this.nextCursor});
}

/// EPIC-M3.11 — repository boundary over `GET /api/v1/system/{health,
/// providers,data-freshness,events}`. Every route is a public, read-only
/// GET (no auth header is required server-side), matching this EPIC's own
/// "health state is read-only to normal users" AC.
class SystemRepository {
  final ApiClient _client;

  SystemRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<SystemHealthSummary> fetchHealth() async {
    final response = await _client.get('/system/health');
    return SystemHealthSummary.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<ProviderStatus>> fetchProviders() async {
    final response = await _client.get('/system/providers');
    return (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(ProviderStatus.fromJson)
        .toList();
  }

  Future<List<DataFreshnessItem>> fetchDataFreshness() async {
    final response = await _client.get('/system/data-freshness');
    return (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(DataFreshnessItem.fromJson)
        .toList();
  }

  Future<SystemEventsPage> fetchEvents({
    String? cursor,
    int pageSize = 20,
  }) async {
    final response = await _client.get(
      '/system/events',
      query: {'pageSize': pageSize.toString(), 'cursor': ?cursor},
    );
    final items = (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(SystemEvent.fromJson)
        .toList();
    return SystemEventsPage(
      items: items,
      nextCursor: response.meta['nextCursor'] as String?,
    );
  }
}

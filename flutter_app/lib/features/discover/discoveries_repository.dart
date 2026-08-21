import '../../core/api_client.dart';
import 'discovery_history_point.dart';
import 'discovery_item.dart';
import 'discovery_summary.dart';

class DiscoveriesPage {
  final List<DiscoveryItem> items;
  final String? nextCursor;
  const DiscoveriesPage({required this.items, required this.nextCursor});
}

/// EPIC-M1.140 (candidates) / EPIC-M3.6 (summary, history) — repository
/// boundary over `GET /api/v1/discovery/{candidates,summary,history}`. No
/// client-side ranking/business logic (M1.140 AC: "UI does not implement
/// discovery/ranking logic locally") -- the lifecycle stage, suppression
/// reason and effectiveness verdicts are all computed server-side.
class DiscoveriesRepository {
  final ApiClient _client;

  DiscoveriesRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<DiscoveriesPage> fetchPage({
    String? market,
    String? sector,
    String? industry,
    String? marketCapBucket,
    String? discoveryBasis,
    int pageSize = 20,
    String? cursor,
  }) async {
    final response = await _client.get(
      '/discovery/candidates',
      query: {
        'pageSize': pageSize.toString(),
        'market': ?market,
        'sector': ?sector,
        'industry': ?industry,
        'marketCap': ?marketCapBucket,
        'discoveryBasis': ?discoveryBasis,
        'cursor': ?cursor,
      },
    );
    final items = (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(DiscoveryItem.fromJson)
        .toList();
    return DiscoveriesPage(
      items: items,
      nextCursor: response.meta['nextCursor'] as String?,
    );
  }

  Future<DiscoverySummary> fetchSummary() async {
    final response = await _client.get('/discovery/summary');
    return DiscoverySummary.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<DiscoveryHistoryPoint>> fetchHistory({int days = 30}) async {
    final response = await _client.get(
      '/discovery/history',
      query: {'days': days.toString()},
    );
    return (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(DiscoveryHistoryPoint.fromJson)
        .toList();
  }
}

import '../../core/api_client.dart';
import 'discovery_item.dart';

class DiscoveriesPage {
  final List<DiscoveryItem> items;
  final String? nextCursor;
  const DiscoveriesPage({required this.items, required this.nextCursor});
}

/// EPIC-M1.140 — repository boundary over EPIC-M1.139's
/// `GET /api/v1/discoveries`. No client-side ranking/business logic
/// (M1.140 AC: "UI does not implement discovery/ranking logic locally").
class DiscoveriesRepository {
  final ApiClient _client;

  DiscoveriesRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<DiscoveriesPage> fetchPage({
    String? market,
    String? sector,
    String? industry,
    String? marketCapBucket,
    String? liquidity,
    double? minScore,
    String sort = 'discoveredAt',
    bool descending = true,
    int pageSize = 20,
    String? cursor,
  }) async {
    final response = await _client.get(
      '/discoveries',
      query: {
        'sort': sort,
        'direction': descending ? 'desc' : 'asc',
        'pageSize': pageSize.toString(),
        'market': ?market,
        'sector': ?sector,
        'industry': ?industry,
        'marketCapBucket': ?marketCapBucket,
        'liquidity': ?liquidity,
        if (minScore != null) 'minScore': minScore.toString(),
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
}

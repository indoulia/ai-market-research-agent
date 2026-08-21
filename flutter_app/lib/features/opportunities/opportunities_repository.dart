import '../../core/api_client.dart';
import '../dashboard/recommendation.dart';

/// EPIC-M3.3 — sort keys accepted by `GET /api/v1/opportunities`. Distinct
/// from `dashboard/recommendations_repository.dart`'s [RecommendationSort]
/// because the Explorer's API contract supports a richer vocabulary
/// (`probability`, `freshness`, `ranking`) that `/recommendations` doesn't.
enum OpportunitySort { trust, score, upside, probability, freshness, ranking }

extension OpportunitySortWire on OpportunitySort {
  String get wireName => switch (this) {
    OpportunitySort.trust => 'trust',
    OpportunitySort.score => 'score',
    OpportunitySort.upside => 'upside',
    OpportunitySort.probability => 'probability',
    OpportunitySort.freshness => 'freshness',
    OpportunitySort.ranking => 'ranking',
  };
}

/// EPIC-M3.3 — one page-based fetch: the items plus enough paging metadata
/// (`page`, `pageSize`, `total`) for both "load more" infinite scroll and an
/// explicit result-count/freshness display, per this endpoint's own
/// documented response contract (`items, page, pageSize, total, asOf,
/// filters`).
class OpportunitiesPage {
  final List<Recommendation> items;
  final int page;
  final int pageSize;
  final int total;
  final DateTime? asOf;

  const OpportunitiesPage({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
    required this.asOf,
  });

  bool get hasMore => page * pageSize < total;
}

/// EPIC-M3.3 — repository boundary over `GET /api/v1/opportunities`.
/// Screens depend on this, never on [ApiClient] directly, mirroring
/// `RecommendationsRepository`/`DiscoveriesRepository`'s existing
/// convention. Reuses `dashboard/recommendation.dart`'s [Recommendation]
/// model for items -- the epic's own contract says items are "the same
/// canonical recommendation summary" M3.2 uses, so a second, parallel
/// model would only be a second thing to keep in sync with the same shape.
class OpportunitiesRepository {
  final ApiClient _client;

  OpportunitiesRepository({ApiClient? client})
    : _client = client ?? ApiClient();

  Future<OpportunitiesPage> fetchPage({
    String? market,
    int? horizon,
    String? sector,
    String? industry,
    String? marketCap,
    double? minTrust,
    double? minScore,
    double? minUpside,
    String? liquidityBucket,
    String? status,
    String? search,
    OpportunitySort sort = OpportunitySort.score,
    bool descending = true,
    int page = 1,
    int pageSize = 20,
  }) async {
    final query = <String, String>{
      'sort': descending ? '-${sort.wireName}' : sort.wireName,
      'page': page.toString(),
      'pageSize': pageSize.toString(),
      'market': ?market,
      'horizon': ?horizon?.toString(),
      if (sector != null && sector.isNotEmpty) 'sector': sector,
      if (industry != null && industry.isNotEmpty) 'industry': industry,
      'marketCap': ?marketCap,
      'minTrust': ?minTrust?.toString(),
      'minScore': ?minScore?.toString(),
      'minUpside': ?minUpside?.toString(),
      'liquidityBucket': ?liquidityBucket,
      'status': ?status,
      if (search != null && search.isNotEmpty) 'search': search,
    };

    final response = await _client.get('/opportunities', query: query);
    final body = response.data as Map<String, dynamic>;
    final items = (body['items'] as List)
        .cast<Map<String, dynamic>>()
        .map(Recommendation.fromJson)
        .toList();

    return OpportunitiesPage(
      items: items,
      page: body['page'] as int,
      pageSize: body['pageSize'] as int,
      total: body['total'] as int,
      asOf: body['asOf'] == null
          ? null
          : DateTime.parse(body['asOf'] as String),
    );
  }
}

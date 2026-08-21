import '../../core/api_client.dart';
import 'recommendation.dart';

/// EPIC-M1.136 — result of one page fetch: items plus the opaque cursor for
/// the next page (`null` on the last page, per EPIC-M1.132's cursor
/// pagination convention). Never re-sorts/re-ranks client-side — the server
/// is the ranking authority (EPIC-M1.135 AC).
class RecommendationsPage {
  final List<Recommendation> items;
  final String? nextCursor;
  final DateTime asOfServerTime;

  const RecommendationsPage({
    required this.items,
    required this.nextCursor,
    required this.asOfServerTime,
  });
}

enum RecommendationSort { score, trust, upside, confidence, updatedAt }

extension on RecommendationSort {
  String get wireName => switch (this) {
    RecommendationSort.score => 'score',
    RecommendationSort.trust => 'trust',
    RecommendationSort.upside => 'upside',
    RecommendationSort.confidence => 'confidence',
    RecommendationSort.updatedAt => 'updatedAt',
  };
}

/// EPIC-M1.136 — repository boundary over EPIC-M1.135's
/// `GET /api/v1/recommendations`. Screens depend on this, never on
/// [ApiClient] directly, so the query-param/response mapping lives in one
/// place.
class RecommendationsRepository {
  final ApiClient _client;

  RecommendationsRepository({ApiClient? client})
    : _client = client ?? ApiClient();

  Future<RecommendationsPage> fetchPage({
    int? horizonDays,
    RecommendationSort sort = RecommendationSort.score,
    bool descending = true,
    int pageSize = 20,
    String? cursor,
  }) async {
    final query = <String, String>{
      'sort': sort.wireName,
      'direction': descending ? 'desc' : 'asc',
      'pageSize': pageSize.toString(),
      if (horizonDays != null) 'horizon': horizonDays.toString(),
      'cursor': ?cursor,
    };

    final response = await _client.get('/recommendations', query: query);
    final items = (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(Recommendation.fromJson)
        .toList();

    return RecommendationsPage(
      items: items,
      nextCursor: response.meta['nextCursor'] as String?,
      asOfServerTime: DateTime.parse(response.meta['timestamp'] as String),
    );
  }
}

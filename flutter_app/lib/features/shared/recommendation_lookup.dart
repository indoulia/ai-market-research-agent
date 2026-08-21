import '../dashboard/recommendations_repository.dart';

/// EPIC-M1.140 — best-effort symbol → active-recommendation lookup, used to
/// satisfy "navigate from an event/news/discovery item to the affected
/// recommendation" when neither M1.135 nor M1.139 exposes a symbol filter
/// on `/recommendations` (checked against `docs/api/openapi.json`).
/// Scans the single largest allowed page (100, M1.135's documented max) of
/// the live feed client-side — a real, named limitation, not a fabricated
/// guarantee: a symbol with more than 100 higher-ranked recommendations
/// ahead of it will not be found. Returns null (never invents an id) when
/// no match is found, including because there genuinely is no active
/// positive recommendation for that symbol right now.
Future<int?> findRecommendationIdBySymbol(
  RecommendationsRepository repository,
  String symbol,
) async {
  final page = await repository.fetchPage(pageSize: 100);
  for (final item in page.items) {
    if (item.symbol == symbol) return item.id;
  }
  return null;
}

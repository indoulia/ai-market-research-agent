import '../../core/api_client.dart';
import 'event_item.dart';
import 'history_item.dart';
import 'recommendation_detail.dart';
import 'recommendation_outcome.dart';

class HistoryPage {
  final List<RecommendationHistoryItem> items;
  final String? nextCursor;
  const HistoryPage({required this.items, required this.nextCursor});
}

class EventsPage {
  final List<RecommendationEventItem> items;
  final String? nextCursor;
  const EventsPage({required this.items, required this.nextCursor});
}

/// EPIC-M1.138 — repository boundary over EPIC-M1.137's four detail/history
/// contracts. Screens depend on this, never on [ApiClient] directly.
class RecommendationDetailRepository {
  final ApiClient _client;

  RecommendationDetailRepository({ApiClient? client})
    : _client = client ?? ApiClient();

  Future<RecommendationDetail> fetchDetail(int id) async {
    final response = await _client.get('/recommendations/$id');
    return RecommendationDetail.fromJson(response.data as Map<String, dynamic>);
  }

  Future<HistoryPage> fetchHistory(
    int id, {
    DateTime? from,
    DateTime? to,
    String? cursor,
    int pageSize = 20,
  }) async {
    final response = await _client.get(
      '/recommendations/$id/history',
      query: {
        'pageSize': pageSize.toString(),
        if (from != null) 'from': from.toUtc().toIso8601String(),
        if (to != null) 'to': to.toUtc().toIso8601String(),
        'cursor': ?cursor,
      },
    );
    final items = (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(RecommendationHistoryItem.fromJson)
        .toList();
    return HistoryPage(
      items: items,
      nextCursor: response.meta['nextCursor'] as String?,
    );
  }

  Future<EventsPage> fetchEvents(
    int id, {
    String? cursor,
    int pageSize = 20,
  }) async {
    final response = await _client.get(
      '/recommendations/$id/events',
      query: {'pageSize': pageSize.toString(), 'cursor': ?cursor},
    );
    final items = (response.data as List)
        .cast<Map<String, dynamic>>()
        .map(RecommendationEventItem.fromJson)
        .toList();
    return EventsPage(
      items: items,
      nextCursor: response.meta['nextCursor'] as String?,
    );
  }

  Future<RecommendationOutcome> fetchOutcome(int id) async {
    final response = await _client.get('/recommendations/$id/outcome');
    return RecommendationOutcome.fromJson(
      response.data as Map<String, dynamic>,
    );
  }
}

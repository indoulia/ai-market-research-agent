import '../../core/api_client.dart';
import 'market_event_item.dart';
import 'news_item.dart';

enum FeedEntryKind { news, corporateAction }

/// EPIC-M1.140 — one row in the unified chronological news+events stream.
/// Wraps either a [NewsItem] or a [MarketEventItem]; screens read [kind] to
/// decide which fields to show rather than duplicating rendering logic.
class FeedEntry {
  final FeedEntryKind kind;
  final DateTime timestamp;
  final String symbol;
  final String headline;
  final String source;
  final String? materiality;
  final int evidenceId;

  const FeedEntry({
    required this.kind,
    required this.timestamp,
    required this.symbol,
    required this.headline,
    required this.source,
    required this.materiality,
    required this.evidenceId,
  });

  factory FeedEntry.fromNews(NewsItem n) => FeedEntry(
    kind: FeedEntryKind.news,
    timestamp: n.publishedAt,
    symbol: n.symbol,
    headline: n.headline,
    source: n.source,
    materiality: n.materiality,
    evidenceId: n.evidenceId,
  );

  factory FeedEntry.fromEvent(MarketEventItem e) => FeedEntry(
    kind: FeedEntryKind.corporateAction,
    timestamp: e.effectiveAt,
    symbol: e.symbol,
    headline: '${e.type.replaceAll('_', ' ')}: ${e.title}',
    source: e.source,
    materiality: e.materiality,
    evidenceId: e.evidenceId,
  );
}

/// EPIC-M1.140 — repository boundary over EPIC-M1.139's `/news` and
/// `/events`. Merges both into one chronological feed client-side — the
/// API deliberately keeps them separate endpoints (different source
/// tables), so the "chronological event stream" UX requirement is a
/// presentation-layer merge, not a contract gap.
class NewsEventsRepository {
  final ApiClient _client;

  NewsEventsRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<List<FeedEntry>> fetchFeed({String? symbol, int pageSize = 20}) async {
    final newsResponse = await _client.get(
      '/news',
      query: {'pageSize': pageSize.toString(), 'symbol': ?symbol},
    );
    final eventsResponse = await _client.get(
      '/events',
      query: {'pageSize': pageSize.toString(), 'symbol': ?symbol},
    );

    final news = (newsResponse.data as List)
        .cast<Map<String, dynamic>>()
        .map(NewsItem.fromJson)
        .map(FeedEntry.fromNews);
    final events = (eventsResponse.data as List)
        .cast<Map<String, dynamic>>()
        .map(MarketEventItem.fromJson)
        .map(FeedEntry.fromEvent);

    final merged = [...news, ...events].toList()
      ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
    return merged;
  }
}

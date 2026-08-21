import '../../core/api_client.dart';
import 'market_event_item.dart';
import 'news_item.dart';

enum FeedEntryKind { news, corporateAction }

/// EPIC-M1.140 — one row in the unified chronological news+events stream.
/// Wraps either a [NewsItem] or a [MarketEventItem]; screens read [kind] to
/// decide which fields to show rather than duplicating rendering logic.
///
/// EPIC-M3.5 added [eventType] (`NewsItem.eventType` for news,
/// `MarketEventItem.type` for corporate actions — filterable via the
/// Type filter bar) and [affectedSecurities] (rendered as chips on the
/// card when a story is linked to more than one symbol).
class FeedEntry {
  final FeedEntryKind kind;
  final DateTime timestamp;
  final String symbol;
  final String headline;
  final String source;
  final String? materiality;
  final String eventType;
  final List<String> affectedSecurities;
  final int evidenceId;

  const FeedEntry({
    required this.kind,
    required this.timestamp,
    required this.symbol,
    required this.headline,
    required this.source,
    required this.materiality,
    required this.eventType,
    required this.affectedSecurities,
    required this.evidenceId,
  });

  factory FeedEntry.fromNews(NewsItem n) => FeedEntry(
    kind: FeedEntryKind.news,
    timestamp: n.publishedAt,
    symbol: n.symbol,
    headline: n.headline,
    source: n.source,
    materiality: n.materiality,
    eventType: n.eventType,
    affectedSecurities: n.affectedSecurities,
    evidenceId: n.evidenceId,
  );

  factory FeedEntry.fromEvent(MarketEventItem e) => FeedEntry(
    kind: FeedEntryKind.corporateAction,
    timestamp: e.effectiveAt,
    symbol: e.symbol,
    headline: '${e.type.replaceAll('_', ' ')}: ${e.title}',
    source: e.source,
    materiality: e.materiality,
    eventType: e.type,
    affectedSecurities: [e.symbol],
    evidenceId: e.evidenceId,
  );
}

/// EPIC-M1.143 — one merged fetch's result, carrying each source's own
/// cursor separately. `/news` and `/events` are independently paginated
/// (different source tables per M1.139), so "load more" must advance
/// each source's cursor on its own rather than a single shared one.
class FeedPage {
  final List<FeedEntry> newEntries;
  final String? nextNewsCursor;
  final String? nextEventsCursor;

  const FeedPage({
    required this.newEntries,
    required this.nextNewsCursor,
    required this.nextEventsCursor,
  });
}

/// EPIC-M1.140/M1.143 — repository boundary over EPIC-M1.139's `/news` and
/// `/events`. Merges both into one chronological feed client-side — the
/// API deliberately keeps them separate endpoints (different source
/// tables), so the "chronological event stream" UX requirement is a
/// presentation-layer merge, not a contract gap. Supports independent
/// per-source cursor pagination (EPIC-M1.143: "lazy loading/pagination
/// for large datasets") — a source whose cursor is already `null` is not
/// re-fetched.
class NewsEventsRepository {
  final ApiClient _client;

  NewsEventsRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<FeedPage> fetchPage({
    String? symbol,
    int pageSize = 20,
    String? newsCursor,
    String? eventsCursor,
    bool fetchNews = true,
    bool fetchEvents = true,
  }) async {
    List<FeedEntry> news = const [];
    String? nextNewsCursor = newsCursor;
    if (fetchNews) {
      final response = await _client.get(
        '/news',
        query: {
          'pageSize': pageSize.toString(),
          'symbol': ?symbol,
          'cursor': ?newsCursor,
        },
      );
      news = (response.data as List)
          .cast<Map<String, dynamic>>()
          .map(NewsItem.fromJson)
          .map(FeedEntry.fromNews)
          .toList();
      nextNewsCursor = response.meta['nextCursor'] as String?;
    }

    List<FeedEntry> events = const [];
    String? nextEventsCursor = eventsCursor;
    if (fetchEvents) {
      final response = await _client.get(
        '/events',
        query: {
          'pageSize': pageSize.toString(),
          'symbol': ?symbol,
          'cursor': ?eventsCursor,
        },
      );
      events = (response.data as List)
          .cast<Map<String, dynamic>>()
          .map(MarketEventItem.fromJson)
          .map(FeedEntry.fromEvent)
          .toList();
      nextEventsCursor = response.meta['nextCursor'] as String?;
    }

    return FeedPage(
      newEntries: [...news, ...events],
      nextNewsCursor: nextNewsCursor,
      nextEventsCursor: nextEventsCursor,
    );
  }
}

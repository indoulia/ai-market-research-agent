import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/recommendations_repository.dart';
import 'package:mra_app/features/news_events/news_events_repository.dart';
import 'package:mra_app/features/news_events/news_events_screen.dart';

class _FakeNewsEventsRepository extends NewsEventsRepository {
  final Future<FeedPage> Function({String? newsCursor, String? eventsCursor})
  onFetch;
  int callCount = 0;

  _FakeNewsEventsRepository(this.onFetch);

  @override
  Future<FeedPage> fetchPage({
    String? symbol,
    int pageSize = 20,
    String? newsCursor,
    String? eventsCursor,
    bool fetchNews = true,
    bool fetchEvents = true,
  }) {
    callCount++;
    return onFetch(newsCursor: newsCursor, eventsCursor: eventsCursor);
  }
}

class _EmptyRecommendationsRepository extends RecommendationsRepository {
  @override
  Future<RecommendationsPage> fetchPage({
    int? horizonDays,
    String? market,
    String? sector,
    String? marketCapBucket,
    RecommendationSort sort = RecommendationSort.score,
    bool descending = true,
    int pageSize = 20,
    String? cursor,
  }) async => RecommendationsPage(
    items: const [],
    nextCursor: null,
    asOfServerTime: DateTime.parse('2026-08-21T09:00:00Z'),
  );
}

FeedEntry _newsEntry({String symbol = 'TATASTEEL', DateTime? timestamp}) =>
    FeedEntry(
      kind: FeedEntryKind.news,
      timestamp: timestamp ?? DateTime.parse('2026-08-20T09:00:00Z'),
      symbol: symbol,
      headline: 'Company announces new plant.',
      source: 'Market Wire',
      materiality: 'HIGH',
      evidenceId: 1,
    );

Widget _wrap(Widget child) {
  return MaterialApp.router(
    theme: MraTheme.light(),
    routerConfig: GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => Scaffold(body: child),
        ),
      ],
    ),
  );
}

void main() {
  testWidgets('renders a chronological feed entry', (tester) async {
    final repo = _FakeNewsEventsRepository(
      ({newsCursor, eventsCursor}) async => FeedPage(
        newEntries: [_newsEntry()],
        nextNewsCursor: null,
        nextEventsCursor: null,
      ),
    );
    await tester.pumpWidget(
      _wrap(
        NewsEventsScreen(
          repository: repo,
          recommendationsRepository: _EmptyRecommendationsRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Company announces new plant.'), findsOneWidget);
    expect(find.textContaining('TATASTEEL'), findsOneWidget);
  });

  testWidgets('shows an empty state when nothing is recorded', (tester) async {
    final repo = _FakeNewsEventsRepository(
      ({newsCursor, eventsCursor}) async => const FeedPage(
        newEntries: [],
        nextNewsCursor: null,
        nextEventsCursor: null,
      ),
    );
    await tester.pumpWidget(
      _wrap(
        NewsEventsScreen(
          repository: repo,
          recommendationsRepository: _EmptyRecommendationsRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('No material news or events recorded yet.'),
      findsOneWidget,
    );
  });

  testWidgets('EPIC-M1.143: scrolling near the bottom loads the next page', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(400, 600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final firstPage = List.generate(
      20,
      (i) => _newsEntry(
        symbol: 'SYM$i',
        timestamp: DateTime.parse(
          '2026-08-20T09:00:00Z',
        ).subtract(Duration(minutes: i)),
      ),
    );
    // Deliberately older than every firstPage item so it sorts to the very
    // bottom of the merged, timestamp-descending list — i.e. exactly where
    // scrolling down should reveal it. (Misnamed "NEWEST" would suggest
    // otherwise; it's the oldest, appended, second-page item.)
    final secondPage = [
      _newsEntry(
        symbol: 'OLDEST_SECOND_PAGE',
        timestamp: DateTime.parse(
          '2026-08-20T09:00:00Z',
        ).subtract(const Duration(minutes: 1000)),
      ),
    ];

    final repo = _FakeNewsEventsRepository(({newsCursor, eventsCursor}) async {
      if (newsCursor == null) {
        return FeedPage(
          newEntries: firstPage,
          nextNewsCursor: 'cursor-2',
          nextEventsCursor: null,
        );
      }
      return FeedPage(
        newEntries: secondPage,
        nextNewsCursor: null,
        nextEventsCursor: null,
      );
    });

    await tester.pumpWidget(
      _wrap(
        NewsEventsScreen(
          repository: repo,
          recommendationsRepository: _EmptyRecommendationsRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('OLDEST_SECOND_PAGE'), findsNothing);

    // Manual drag-and-check loop: scrollUntilVisible/dragUntilVisible were
    // flaky in this harness once the list rebuilds mid-scroll (the target
    // element goes stale between iterations), so drive it directly.
    final listFinder = find.byType(ListView);
    for (var i = 0; i < 20; i++) {
      await tester.drag(listFinder, const Offset(0, -300));
      await tester.pump();
      if (find.textContaining('OLDEST_SECOND_PAGE').evaluate().isNotEmpty) {
        break;
      }
    }
    await tester.pumpAndSettle();

    expect(find.textContaining('OLDEST_SECOND_PAGE'), findsOneWidget);
    expect(repo.callCount, 2);
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/recommendations_repository.dart';
import 'package:mra_app/features/news_events/news_events_repository.dart';
import 'package:mra_app/features/news_events/news_events_screen.dart';

class _FakeNewsEventsRepository extends NewsEventsRepository {
  final Future<List<FeedEntry>> Function() onFetch;
  _FakeNewsEventsRepository(this.onFetch);

  @override
  Future<List<FeedEntry>> fetchFeed({String? symbol, int pageSize = 20}) =>
      onFetch();
}

class _EmptyRecommendationsRepository extends RecommendationsRepository {
  @override
  Future<RecommendationsPage> fetchPage({
    int? horizonDays,
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

FeedEntry _newsEntry() => FeedEntry(
  kind: FeedEntryKind.news,
  timestamp: DateTime.parse('2026-08-20T09:00:00Z'),
  symbol: 'TATASTEEL',
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
    final repo = _FakeNewsEventsRepository(() async => [_newsEntry()]);
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
    final repo = _FakeNewsEventsRepository(() async => []);
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
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/design_system/components/mra_search_field.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/dashboard_repository.dart';
import 'package:mra_app/features/dashboard/dashboard_screen.dart';
import 'package:mra_app/features/dashboard/dashboard_snapshot.dart';
import 'package:mra_app/features/dashboard/recommendation.dart';
import 'package:mra_app/features/dashboard/recommendations_repository.dart';

Map<String, dynamic> _opportunity({
  int id = 1,
  String symbol = 'TATASTEEL',
  String name = 'Tata Steel Ltd.',
  double? trustScore = 0.65,
  String status = 'ISSUED',
  String updatedAt = '2026-08-21T09:00:00Z',
}) {
  return {
    'id': id,
    'symbol': symbol,
    'name': name,
    'price': '168.35',
    'targetPrice': '176.50',
    'stopLoss': '163.00',
    'horizon': 3,
    'upsidePercent': '4.8',
    'score': '82',
    'confidence': '71',
    'trustScore': trustScore?.toString(),
    'status': status,
    'updatedAt': updatedAt,
  };
}

Map<String, dynamic> _snapshotJson({
  List<Map<String, dynamic>>? topOpportunities,
  List<Map<String, dynamic>> events = const [],
  List<Map<String, dynamic>>? recentChanges,
  String marketStatus = 'UNKNOWN',
  String? marketRegime = 'RISK_ON',
  double? trustScore = 0.7,
  bool smallSample = false,
}) {
  final top = topOpportunities ?? [_opportunity()];
  return {
    'marketStatus': marketStatus,
    'asOf': '2026-08-21T09:00:00Z',
    'marketRegime': marketRegime,
    'indices': [],
    'topOpportunities': top,
    'importantEvents': events,
    'recentChanges': recentChanges ?? top,
    'trustSummary': {
      'trustScore': trustScore?.toString(),
      'trustDelta': '0.02',
      'calibrationScore': '0.05',
      'sampleSize': 12,
      'smallSample': smallSample,
      'modelVersion': 'test-model-1',
    },
    'dataFreshness': {
      'opportunitiesAsOf': '2026-08-21T09:00:00Z',
      'marketAsOf': '2026-08-21T09:00:00Z',
      'newsAsOf': null,
    },
  };
}

class _FakeDashboardRepository extends DashboardRepository {
  final Future<DashboardSnapshot> Function() onFetch;
  _FakeDashboardRepository(this.onFetch);

  @override
  Future<DashboardSnapshot> fetchSnapshot({
    String? market,
    int? horizonDays,
    String? sector,
    String? marketCapBucket,
    int limit = 10,
  }) => onFetch();
}

class _FakeRecommendationsRepository extends RecommendationsRepository {
  final Future<RecommendationsPage> Function() onFetch;
  _FakeRecommendationsRepository(this.onFetch);

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
  }) => onFetch();
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

DashboardSnapshot _snapshotOf(Map<String, dynamic> json) =>
    DashboardSnapshot.fromJson(json);

void main() {
  testWidgets('shows skeleton loaders while the snapshot is in flight', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () => Future.delayed(
        const Duration(milliseconds: 500),
        () => _snapshotOf(_snapshotJson()),
      ),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pump();

    expect(find.text('TATASTEEL'), findsNothing);
    await tester.pumpAndSettle();
    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets('renders opportunities, market status and trust summary', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(
        _snapshotJson(
          topOpportunities: [
            _opportunity(id: 1),
            _opportunity(id: 2, symbol: 'INFY'),
          ],
        ),
      ),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
    expect(find.text('INFY'), findsOneWidget);
    expect(find.textContaining('RISK_ON'), findsOneWidget);
    expect(find.textContaining('Trust:'), findsOneWidget);
  });

  testWidgets(
    'sector filter reuses the shared MraSearchField and refetches on submit',
    (tester) async {
      var fetchCount = 0;
      final repo = _FakeDashboardRepository(() async {
        fetchCount++;
        return _snapshotOf(_snapshotJson());
      });
      await tester.pumpWidget(
        _wrap(DashboardScreen(dashboardRepository: repo)),
      );
      await tester.pumpAndSettle();

      // A hand-rolled duplicate TextField would satisfy the hint-text
      // check but not this type check -- this is what would have failed
      // before switching dashboard_screen.dart to the shared component.
      final sectorField = find.widgetWithText(
        MraSearchField,
        'Filter by sector',
      );
      expect(sectorField, findsOneWidget);
      expect(fetchCount, 1);

      await tester.enterText(sectorField, 'Energy');
      await tester.testTextInput.receiveAction(TextInputAction.search);
      await tester.pumpAndSettle();

      expect(fetchCount, 2);
    },
  );

  testWidgets('renders the important-events strip when events are present', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(
        _snapshotJson(
          events: [
            {
              'kind': 'NEWS',
              'symbol': 'TATASTEEL',
              'title': 'Quarterly results beat estimates',
              'occurredAt': '2026-08-21T08:00:00Z',
              'source': 'test-source',
              'materiality': 'HIGH',
            },
          ],
        ),
      ),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Quarterly results beat estimates'),
      findsOneWidget,
    );
  });

  testWidgets('omits the events strip entirely when there are no events', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(_snapshotJson(events: const [])),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Recently changed'), findsOneWidget);
    // The market/size quick-filter bars are themselves horizontal
    // `ListView`s, so only their fixed count (2) should be present -- a
    // third would mean the events strip rendered despite an empty list.
    expect(find.byType(ListView), findsNWidgets(2));
  });

  testWidgets('renders the recently-changed widget', (tester) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(
        _snapshotJson(recentChanges: [_opportunity(id: 9, symbol: 'WIPRO')]),
      ),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Recently changed'), findsOneWidget);
    expect(find.textContaining('WIPRO'), findsWidgets);

    // EPIC-M3.16 follow-up: this compact card header uses the same
    // titleMedium role as the equivalent "Sector leaders"/"Sector
    // laggards" headers on the market screen and the tracking trend
    // card, not a smaller one-off scale step.
    final theme = Theme.of(tester.element(find.text('Recently changed')));
    final headerText = tester.widget<Text>(find.text('Recently changed'));
    expect(headerText.style, theme.textTheme.titleMedium);
  });

  testWidgets('shows a small-sample badge when trust sample is small', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(_snapshotJson(smallSample: true)),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Small sample'), findsOneWidget);
  });

  testWidgets('shows an error state with retry on fetch failure', (
    tester,
  ) async {
    var attempts = 0;
    final repo = _FakeDashboardRepository(() async {
      attempts++;
      if (attempts == 1) {
        throw const ApiException(code: 'MRA_INTERNAL', message: 'Boom');
      }
      return _snapshotOf(_snapshotJson());
    });
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Boom'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets('shows an empty state when zero opportunities are returned', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(
        _snapshotJson(topOpportunities: const [], recentChanges: const []),
      ),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.text('No positive opportunities match these filters.'),
      findsOneWidget,
    );
  });

  testWidgets('renders an explicit N/A trust indicator, not a fake score', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(
        _snapshotJson(topOpportunities: [_opportunity(trustScore: null)]),
      ),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(dashboardRepository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('N/A'), findsOneWidget);
  });

  testWidgets('tapping a card pushes the recommendation detail route', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async =>
          _snapshotOf(_snapshotJson(topOpportunities: [_opportunity(id: 42)])),
    );
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/home',
          builder: (context, state) =>
              Scaffold(body: DashboardScreen(dashboardRepository: repo)),
          routes: [
            GoRoute(
              path: 'recommendation/:id',
              builder: (context, state) =>
                  Scaffold(body: Text('detail:${state.pathParameters['id']}')),
            ),
          ],
        ),
      ],
      initialLocation: '/home',
    );

    await tester.pumpWidget(
      MaterialApp.router(theme: MraTheme.light(), routerConfig: router),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('TATASTEEL'));
    await tester.pumpAndSettle();

    expect(find.text('detail:42'), findsOneWidget);
  });

  testWidgets(
    'Load more opportunities bootstraps a cursor from /recommendations and '
    'appends only genuinely new rows',
    (tester) async {
      final dashboardRepo = _FakeDashboardRepository(
        () async =>
            _snapshotOf(_snapshotJson(topOpportunities: [_opportunity(id: 1)])),
      );
      var call = 0;
      final recRepo = _FakeRecommendationsRepository(() async {
        call++;
        if (call == 1) {
          // Bootstrap call: identical page-1 result as the snapshot, so it
          // must be deduped to zero *new* rows, then fall through.
          return RecommendationsPage(
            items: [Recommendation.fromJson(_recommendationJson(id: 1))],
            nextCursor: 'cursor-1',
            asOfServerTime: DateTime.parse('2026-08-21T09:00:00Z'),
          );
        }
        return RecommendationsPage(
          items: [
            Recommendation.fromJson(_recommendationJson(id: 2, symbol: 'INFY')),
          ],
          nextCursor: null,
          asOfServerTime: DateTime.parse('2026-08-21T09:00:00Z'),
        );
      });

      await tester.pumpWidget(
        _wrap(
          DashboardScreen(
            dashboardRepository: dashboardRepo,
            repository: recRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // The footer sits below the header widgets in the scroll view; bring
      // it into view before tapping (sliver lists build lazily). Drag the
      // outermost `CustomScrollView` directly rather than
      // `scrollUntilVisible` -- the market/size filter bars are their own
      // (horizontal) `Scrollable`s, which makes the default finder there
      // ambiguous.
      await tester.drag(find.byType(CustomScrollView), const Offset(0, -1000));
      await tester.pumpAndSettle();
      expect(find.text('Load more opportunities'), findsOneWidget);
      // EPIC-M3.16 follow-up: "Load more" is an OutlinedButton everywhere
      // else it appears (tracking, feedback history, system health) — this
      // screen previously used a TextButton for the identical action.
      expect(
        find.ancestor(
          of: find.text('Load more opportunities'),
          matching: find.byType(OutlinedButton),
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('Load more opportunities'));
      await tester.pumpAndSettle();

      expect(find.text('INFY'), findsOneWidget);
      expect(find.text('You’re all caught up'), findsOneWidget);
    },
  );

  testWidgets(
    'EPIC-M1.143: header and widgets survive 2x text scaling at compact '
    'width without overflow',
    (tester) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      final repo = _FakeDashboardRepository(
        () async => _snapshotOf(_snapshotJson()),
      );
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(
            size: Size(360, 800),
            textScaler: TextScaler.linear(2.0),
          ),
          child: _wrap(DashboardScreen(dashboardRepository: repo)),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'EPIC-M1.143: renders a realistic 50-item page without overflow or '
    'exceptions',
    (tester) async {
      final repo = _FakeDashboardRepository(
        () async => _snapshotOf(
          _snapshotJson(
            topOpportunities: List.generate(
              50,
              (i) => _opportunity(id: i, symbol: 'SYM$i'),
            ),
          ),
        ),
      );
      await tester.pumpWidget(
        _wrap(DashboardScreen(dashboardRepository: repo)),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('SYM0'), findsOneWidget);
    },
  );
}

Map<String, dynamic> _recommendationJson({
  int id = 1,
  String symbol = 'TATASTEEL',
}) {
  return {
    'id': id,
    'symbol': symbol,
    'exchange': 'NSE',
    'companyName': '$symbol Ltd.',
    'asOf': '2026-08-21T09:00:00Z',
    'price': '168.35',
    'changePct': '1.42',
    'recommendation': 'POSITIVE_OPPORTUNITY',
    'horizonDays': 3,
    'targetPrice': '176.50',
    'stopLoss': '163.00',
    'upsidePct': '4.8',
    'probability': '0.7',
    'score': '82',
    'confidence': '71',
    'trustScore': '0.65',
    'uncertaintyLevel': 'LOW',
    'fundamentalSummary': null,
    'newsSummary': null,
    'eventSummary': null,
    'marketSummary': null,
    'evidenceFreshness': 'FRESH',
    'status': 'ISSUED',
    'predictionVersion': {
      'modelVersion': '1',
      'featureVersion': '1',
      'consensusContractVersion': '1',
      'horizonSelectionVersion': '1',
      'scoringContractVersion': '1',
      'rankingVersion': '1',
    },
    'updatedAt': '2026-08-21T09:00:00Z',
  };
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/design_system/components/mra_search_field.dart';
import 'package:mra_app/design_system/components/recommendation_card.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/dashboard_repository.dart';
import 'package:mra_app/features/dashboard/dashboard_screen.dart';
import 'package:mra_app/features/dashboard/dashboard_snapshot.dart';
import 'package:mra_app/features/dashboard/recommendation.dart';
import 'package:mra_app/features/dashboard/recommendations_repository.dart';
import 'package:mra_app/features/tracking/tracked_prediction.dart';
import 'package:mra_app/features/tracking/tracking_filters.dart';
import 'package:mra_app/features/tracking/tracking_repository.dart';
import 'package:mra_app/features/tracking/tracking_summary.dart';

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

Map<String, dynamic> _closedPredictionJson({
  int id = 1,
  String symbol = 'HCLTECH',
  String? outcome = 'TARGET_HIT',
}) {
  return {
    'id': id,
    'symbol': symbol,
    'status': 'CLOSED',
    'asOf': '2026-08-21T09:00:00Z',
    'horizonDays': 5,
    'predictedReturn': '4.2',
    'realizedReturn': '4.9',
    'outcome': outcome,
    'modelVersion': 'test-model-1',
  };
}

/// EPIC-173 — a quiet stand-in for [TrackingRepository] so tests never hit
/// the real network (the default no-arg behavior throws, exercising the
/// Performance card's graceful-degradation path by default).
class _FakeTrackingRepository extends TrackingRepository {
  final Future<TrackingSummary> Function() onSummary;
  final Future<TrackedPredictionsPage> Function() onPredictions;

  _FakeTrackingRepository({
    Future<TrackingSummary> Function()? onSummary,
    Future<TrackedPredictionsPage> Function()? onPredictions,
  }) : onSummary = onSummary ?? (() async => throw Exception('unavailable')),
       onPredictions =
           onPredictions ??
           (() async =>
               const TrackedPredictionsPage(items: [], nextCursor: null));

  @override
  Future<TrackingSummary> fetchSummary({
    required String range,
    TrackingFilters filters = const TrackingFilters(),
  }) => onSummary();

  @override
  Future<TrackedPredictionsPage> fetchPredictions({
    required String status,
    String? cursor,
    int pageSize = 10,
    TrackingFilters filters = const TrackingFilters(),
  }) => onPredictions();
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
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
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
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
    expect(find.text('INFY'), findsOneWidget);
    expect(find.textContaining('RISK_ON'), findsOneWidget);

    // EPIC-173: the Performance card (Trust summary) now sits in the watch
    // rail below the grid at this (medium) width -- scroll to see it.
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
    await tester.pumpAndSettle();
    expect(find.textContaining('Trust score'), findsOneWidget);
    expect(find.text('70%'), findsOneWidget);
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
        _wrap(
          DashboardScreen(
            dashboardRepository: repo,
            trackingRepository: _FakeTrackingRepository(),
          ),
        ),
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
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // EPIC-173: important events are now a vertical card in the watch rail.
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
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
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
    await tester.pumpAndSettle();

    expect(find.text('Recently changed'), findsOneWidget);
    // EPIC-173: an empty `importantEvents` list means the events card
    // itself is omitted from the watch rail entirely.
    expect(find.text('Important events'), findsNothing);
  });

  testWidgets('renders the recently-changed widget', (tester) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(
        _snapshotJson(recentChanges: [_opportunity(id: 9, symbol: 'WIPRO')]),
      ),
    );
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
    await tester.pumpAndSettle();

    // EPIC-173: "Recently changed" is now the Activity card's default tab.
    expect(find.text('Recently changed'), findsOneWidget);
    expect(find.textContaining('WIPRO'), findsWidgets);
  });

  testWidgets(
    'Activity card switches between recently-changed and closed calls',
    (tester) async {
      final repo = _FakeDashboardRepository(
        () async => _snapshotOf(
          _snapshotJson(recentChanges: [_opportunity(id: 9, symbol: 'WIPRO')]),
        ),
      );
      final tracking = _FakeTrackingRepository(
        onPredictions: () async => TrackedPredictionsPage(
          items: [
            TrackedPrediction.fromJson(
              _closedPredictionJson(symbol: 'HCLTECH'),
            ),
          ],
          nextCursor: null,
        ),
      );
      await tester.pumpWidget(
        _wrap(
          DashboardScreen(
            dashboardRepository: repo,
            trackingRepository: tracking,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
      await tester.pumpAndSettle();

      expect(find.textContaining('WIPRO'), findsWidgets);
      expect(find.textContaining('HCLTECH'), findsNothing);

      await tester.tap(find.text('Closed calls'));
      await tester.pumpAndSettle();

      expect(find.textContaining('HCLTECH'), findsOneWidget);
    },
  );

  testWidgets('shows a small-sample badge when trust sample is small', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(_snapshotJson(smallSample: true)),
    );
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
    await tester.pumpAndSettle();

    expect(find.text('Small sample'), findsOneWidget);
  });

  testWidgets(
    'Performance card degrades to trust-only when tracking summary fails',
    (tester) async {
      final repo = _FakeDashboardRepository(
        () async => _snapshotOf(_snapshotJson()),
      );
      await tester.pumpWidget(
        _wrap(
          DashboardScreen(
            dashboardRepository: repo,
            trackingRepository: _FakeTrackingRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
      await tester.pumpAndSettle();

      expect(find.text('70%'), findsOneWidget);
      expect(find.textContaining('hit target'), findsNothing);
    },
  );

  testWidgets('the how-Marksy-works strip can be dismissed', (tester) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(_snapshotJson()),
    );
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Score every stock'), findsOneWidget);

    await tester.tap(find.byTooltip('Dismiss'));
    await tester.pumpAndSettle();

    expect(find.text('Score every stock'), findsNothing);
  });

  testWidgets('the coming-soon card switches between IPO and NFO', (
    tester,
  ) async {
    final repo = _FakeDashboardRepository(
      () async => _snapshotOf(_snapshotJson()),
    );
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -3000));
    await tester.pumpAndSettle();

    expect(find.textContaining('mainboard'), findsOneWidget);

    await tester.tap(find.text('NFO'));
    await tester.pumpAndSettle();

    expect(find.textContaining('New Fund Offer'), findsOneWidget);
  });

  testWidgets(
    'compact width renders the dense opportunity row, not the full card',
    (tester) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      final repo = _FakeDashboardRepository(
        () async => _snapshotOf(_snapshotJson()),
      );
      await tester.pumpWidget(
        _wrap(
          DashboardScreen(
            dashboardRepository: repo,
            trackingRepository: _FakeTrackingRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('TATASTEEL'), findsOneWidget);
      // The full desktop/tablet card renders a sparkline; the compact row
      // deliberately drops it to fit roughly twice as many rows per screen.
      expect(find.byType(RecommendationCard), findsNothing);
    },
  );

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
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
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
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
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
    await tester.pumpWidget(
      _wrap(
        DashboardScreen(
          dashboardRepository: repo,
          trackingRepository: _FakeTrackingRepository(),
        ),
      ),
    );
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
          builder: (context, state) => Scaffold(
            body: DashboardScreen(
              dashboardRepository: repo,
              trackingRepository: _FakeTrackingRepository(),
            ),
          ),
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
            trackingRepository: _FakeTrackingRepository(),
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
          child: _wrap(
            DashboardScreen(
              dashboardRepository: repo,
              trackingRepository: _FakeTrackingRepository(),
            ),
          ),
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
        _wrap(
          DashboardScreen(
            dashboardRepository: repo,
            trackingRepository: _FakeTrackingRepository(),
          ),
        ),
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

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/design_system.dart';
import 'package:mra_app/features/tracking/active_prediction.dart';
import 'package:mra_app/features/tracking/tracked_prediction.dart';
import 'package:mra_app/features/tracking/tracking_breakdown.dart';
import 'package:mra_app/features/tracking/tracking_repository.dart';
import 'package:mra_app/features/tracking/tracking_screen.dart';
import 'package:mra_app/features/tracking/tracking_summary.dart';
import 'package:mra_app/features/tracking/tracking_timeseries.dart';

class _FakeTrackingRepository extends TrackingRepository {
  final List<String> summaryRangeCalls = [];
  final List<String> timeseriesMetricCalls = [];
  final List<String> breakdownDimensionCalls = [];

  TrackingSummary Function(String range) summaryFor;
  TrackingBreakdown Function(String dimension) breakdownFor;
  TrackedPredictionsPage Function(String? cursor) predictionsFor;
  ActivePredictionsPage Function(String? cursor) activePredictionsFor;
  ActivePrediction Function(int predictionId)? activePredictionFor;

  _FakeTrackingRepository({
    required this.summaryFor,
    required this.breakdownFor,
    required this.predictionsFor,
    ActivePredictionsPage Function(String? cursor)? activePredictionsFor,
    this.activePredictionFor,
  }) : activePredictionsFor =
           activePredictionsFor ??
           ((_) => const ActivePredictionsPage(items: [], nextCursor: null));

  @override
  Future<TrackingSummary> fetchSummary({required String range}) async {
    summaryRangeCalls.add(range);
    return summaryFor(range);
  }

  @override
  Future<TrackingTimeseries> fetchTimeseries({
    required String metric,
    required String range,
    required String bucket,
  }) async {
    timeseriesMetricCalls.add(metric);
    return _timeseries(metric);
  }

  @override
  Future<TrackingBreakdown> fetchBreakdown({required String dimension}) async {
    breakdownDimensionCalls.add(dimension);
    return breakdownFor(dimension);
  }

  @override
  Future<TrackedPredictionsPage> fetchPredictions({
    required String status,
    String? cursor,
    int pageSize = 10,
  }) async => predictionsFor(cursor);

  @override
  Future<ActivePredictionsPage> fetchActivePredictions({
    String? cursor,
    int pageSize = 10,
  }) async => activePredictionsFor(cursor);

  @override
  Future<ActivePrediction> fetchActivePrediction(int predictionId) async {
    final override = activePredictionFor;
    if (override != null) return override(predictionId);
    return _activePrediction(id: predictionId);
  }
}

TrackingSummary _summary({
  bool smallSample = false,
  String? trustDelta = '0.02',
}) {
  return TrackingSummary.fromJson({
    'range': '30d',
    'predictionCount': 25,
    'closedCount': 10,
    'targetHitRate': '0.4',
    'stopLossRate': '0.1',
    'horizonExpiryRate': '0.5',
    'avgRealizedReturn': '0.032',
    'avgPredictedReturn': '0.05',
    'calibrationScore': '0.08',
    'trustScore': '0.72',
    'trustDelta': trustDelta,
    'modelVersion': 'v3',
    'benchmarkReturn': null,
    'relativeReturn': null,
    'smallSample': smallSample,
  });
}

TrackingTimeseries _timeseries(String metric) {
  return TrackingTimeseries.fromJson({
    'metric': metric,
    'range': '30d',
    'bucket': 'day',
    'points': [
      {'bucketStart': '2026-08-01T00:00:00Z', 'value': '0.6', 'sampleCount': 5},
      {'bucketStart': '2026-08-02T00:00:00Z', 'value': '0.7', 'sampleCount': 6},
    ],
  });
}

TrackingBreakdown _breakdown(String dimension, {String key = '3D'}) {
  return TrackingBreakdown.fromJson({
    'dimension': dimension,
    'items': [
      {
        'key': key,
        'predictionCount': 12,
        'closedCount': 6,
        'targetHitRate': '0.5',
        'avgRealizedReturn': '0.02',
        'smallSample': false,
      },
    ],
  });
}

TrackedPredictionsPage _predictionsPage({String? nextCursor, int id = 101}) {
  return TrackedPredictionsPage(
    items: [
      TrackedPrediction.fromJson({
        'id': id,
        'symbol': 'TATASTEEL',
        'status': 'closed',
        'asOf': '2026-08-01T00:00:00Z',
        'horizonDays': 5,
        'predictedReturn': '0.05',
        'realizedReturn': '0.03',
        'outcome': 'TARGET_HIT',
        'modelVersion': 'v3',
      }),
    ],
    nextCursor: nextCursor,
  );
}

ActivePrediction _activePrediction({
  int id = 501,
  String symbol = 'INFY',
  String status = 'ACTIVE',
}) {
  return ActivePrediction.fromJson({
    'predictionId': id,
    'symbol': symbol,
    'companyName': '$symbol Ltd',
    'exchange': 'NSE',
    'price': '105.00',
    'targetPrice': '120.00',
    'stopLoss': '95.00',
    'horizon': 5,
    'remainingTradingDays': 3,
    'distanceToTargetPercent': '14.3',
    'distanceToStopLossPercent': '9.5',
    'score': '0.8',
    'confidence': '0.75',
    'trustScore': '0.82',
    'status': status,
    'lastPriceAt': '2026-08-20T10:00:00Z',
    'lastRevisionAt': null,
    'nextEvaluationAt': '2026-08-21T09:15:00Z',
  });
}

_FakeTrackingRepository _defaultRepo({
  bool smallSample = false,
  String? nextCursor,
}) {
  return _FakeTrackingRepository(
    summaryFor: (_) => _summary(smallSample: smallSample),
    breakdownFor: (dimension) => _breakdown(dimension),
    predictionsFor: (cursor) => _predictionsPage(nextCursor: nextCursor),
  );
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets(
    'renders KPI grid, model version and trend charts from the real contract',
    (tester) async {
      final repo = _defaultRepo();
      await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('15'), findsOneWidget); // Active = 25 - 10
      expect(find.text('10'), findsOneWidget); // Closed
      expect(find.text('40.0%'), findsOneWidget); // targetHitRate
      expect(find.text('72.0%'), findsOneWidget); // trustScore
      expect(find.text('Model: v3'), findsOneWidget);
      expect(find.text('Trust Score trend'), findsOneWidget);
      expect(find.text('Target-hit rate trend'), findsOneWidget);
    },
  );

  testWidgets('shows the small-sample warning only when the summary flags it', (
    tester,
  ) async {
    final repo = _defaultRepo(smallSample: true);
    await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.text('Small sample this period — rates may be volatile'),
      findsOneWidget,
    );
  });

  testWidgets('hides the small-sample warning when not flagged', (
    tester,
  ) async {
    final repo = _defaultRepo();
    await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.text('Small sample this period — rates may be volatile'),
      findsNothing,
    );
  });

  testWidgets('changing the range refetches the summary with the new range', (
    tester,
  ) async {
    final repo = _defaultRepo();
    await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
    await tester.pumpAndSettle();
    expect(repo.summaryRangeCalls, ['30d']);

    await tester.tap(find.text('90 days'));
    await tester.pumpAndSettle();

    expect(repo.summaryRangeCalls, ['30d', '90d']);
  });

  testWidgets('switching the secondary metric refetches only that timeseries', (
    tester,
  ) async {
    final repo = _defaultRepo();
    await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
    await tester.pumpAndSettle();
    expect(repo.timeseriesMetricCalls, ['trust', 'hitRate']);

    await tester.ensureVisible(find.text('Realized return'));
    await tester.tap(find.text('Realized return'));
    await tester.pumpAndSettle();

    expect(repo.timeseriesMetricCalls, ['trust', 'hitRate', 'return']);
    expect(repo.summaryRangeCalls, ['30d']); // unaffected
  });

  testWidgets(
    'switching the breakdown dimension refetches breakdown and shows its items',
    (tester) async {
      final repo = _FakeTrackingRepository(
        summaryFor: (_) => _summary(),
        breakdownFor: (dimension) => _breakdown(
          dimension,
          key: switch (dimension) {
            'sector' => 'IT',
            'stock' => 'AAA',
            _ => '3D',
          },
        ),
        predictionsFor: (_) => _predictionsPage(),
      );
      await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
      await tester.pumpAndSettle();
      expect(find.text('3D'), findsOneWidget);

      await tester.ensureVisible(find.text('Sector'));
      await tester.tap(find.text('Sector'));
      await tester.pumpAndSettle();

      expect(repo.breakdownDimensionCalls, ['horizon', 'sector']);
      expect(find.text('IT'), findsOneWidget);

      // EPIC-M3.7: "stock" is a breakdown dimension option too.
      await tester.ensureVisible(find.text('Stock'));
      await tester.tap(find.text('Stock'));
      await tester.pumpAndSettle();

      expect(repo.breakdownDimensionCalls, ['horizon', 'sector', 'stock']);
      expect(find.text('AAA'), findsOneWidget);
    },
  );

  testWidgets(
    'shows Load more when a next cursor exists and appends the next page',
    (tester) async {
      var page = 0;
      final repo = _FakeTrackingRepository(
        summaryFor: (_) => _summary(),
        breakdownFor: (dimension) => _breakdown(dimension),
        predictionsFor: (cursor) {
          page++;
          return page == 1
              ? _predictionsPage(nextCursor: 'cursor-2', id: 101)
              : _predictionsPage(nextCursor: null, id: 202);
        },
      );
      await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Load more'), findsOneWidget);
      expect(find.text('You’re all caught up'), findsNothing);

      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();

      expect(find.text('TATASTEEL'), findsNWidgets(2));
      expect(find.text('You’re all caught up'), findsOneWidget);
    },
  );

  testWidgets('shows an empty state when there are no closed predictions', (
    tester,
  ) async {
    final repo = _FakeTrackingRepository(
      summaryFor: (_) => _summary(),
      breakdownFor: (dimension) => _breakdown(dimension),
      predictionsFor: (_) =>
          const TrackedPredictionsPage(items: [], nextCursor: null),
    );
    await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('No closed predictions yet.'), findsOneWidget);
  });

  testWidgets('shows an error state and retries on demand', (tester) async {
    var attempt = 0;
    final repo = _FakeTrackingRepository(
      summaryFor: (_) {
        attempt++;
        if (attempt == 1) throw Exception('boom');
        return _summary();
      },
      breakdownFor: (dimension) => _breakdown(dimension),
      predictionsFor: (_) => _predictionsPage(),
    );
    await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('Model: v3'), findsOneWidget);
  });

  testWidgets(
    'tapping a closed prediction pushes the recommendation detail route',
    (tester) async {
      final repo = _defaultRepo();
      final router = GoRouter(
        routes: [
          GoRoute(
            path: '/tracking',
            builder: (context, state) =>
                Scaffold(body: TrackingScreen(repository: repo)),
            routes: [
              GoRoute(
                path: 'recommendation/:id',
                builder: (context, state) => Scaffold(
                  body: Text('detail:${state.pathParameters['id']}'),
                ),
              ),
            ],
          ),
        ],
        initialLocation: '/tracking',
      );

      await tester.pumpWidget(
        MaterialApp.router(theme: MraTheme.light(), routerConfig: router),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('TATASTEEL'));
      await tester.tap(find.text('TATASTEEL'));
      await tester.pumpAndSettle();

      expect(find.text('detail:101'), findsOneWidget);
    },
  );

  testWidgets(
    'EPIC-M1.143: KPI grid and breakdown cards survive 2x text scaling at narrow width',
    (tester) async {
      final repo = _defaultRepo(nextCursor: 'more');
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(
            size: Size(360, 800),
            textScaler: TextScaler.linear(2.0),
          ),
          child: _wrap(TrackingScreen(repository: repo)),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    },
  );

  group('EPIC-M3.8 active positions section', () {
    testWidgets('shows an empty state when there are no active positions', (
      tester,
    ) async {
      final repo = _defaultRepo();
      await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Active positions'), findsOneWidget);
      expect(find.text('No active positions right now.'), findsOneWidget);
    });

    testWidgets(
      'renders an active prediction card with price/target/SL/status',
      (tester) async {
        final repo = _FakeTrackingRepository(
          summaryFor: (_) => _summary(),
          breakdownFor: (dimension) => _breakdown(dimension),
          predictionsFor: (_) => _predictionsPage(),
          activePredictionsFor: (_) => ActivePredictionsPage(
            items: [_activePrediction()],
            nextCursor: null,
          ),
        );
        await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
        await tester.pumpAndSettle();

        expect(find.text('INFY'), findsOneWidget);
        expect(find.textContaining('Target 120.00'), findsOneWidget);
        expect(find.textContaining('SL 95.00'), findsOneWidget);
        expect(find.widgetWithText(MraChip, 'Active'), findsOneWidget);
        expect(find.text('3/5D remaining'), findsOneWidget);
      },
    );

    testWidgets('shows the M1.119-sourced status label, not a recomputed one', (
      tester,
    ) async {
      final repo = _FakeTrackingRepository(
        summaryFor: (_) => _summary(),
        breakdownFor: (dimension) => _breakdown(dimension),
        predictionsFor: (_) => _predictionsPage(),
        activePredictionsFor: (_) => ActivePredictionsPage(
          items: [_activePrediction(status: 'TARGET_HIT')],
          nextCursor: null,
        ),
      );
      await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Target hit'), findsOneWidget);
    });

    testWidgets('tapping a card opens the detail sheet via a fresh fetch', (
      tester,
    ) async {
      final requestedIds = <int>[];
      final repo = _FakeTrackingRepository(
        summaryFor: (_) => _summary(),
        breakdownFor: (dimension) => _breakdown(dimension),
        predictionsFor: (_) => _predictionsPage(),
        activePredictionsFor: (_) => ActivePredictionsPage(
          items: [_activePrediction(id: 777, symbol: 'TCS')],
          nextCursor: null,
        ),
        activePredictionFor: (id) {
          requestedIds.add(id);
          return _activePrediction(id: id, symbol: 'TCS');
        },
      );
      await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
      await tester.pumpAndSettle();

      await tester.tap(find.text('TCS'));
      await tester.pumpAndSettle();

      expect(requestedIds, [777]);
      expect(
        find.text('Next evaluation: 2026-08-21 09:15:00.000Z'),
        findsOneWidget,
      );
    });

    testWidgets('selecting a refresh interval starts periodic polling', (
      tester,
    ) async {
      var fetchCount = 0;
      final repo = _FakeTrackingRepository(
        summaryFor: (_) => _summary(),
        breakdownFor: (dimension) => _breakdown(dimension),
        predictionsFor: (_) => _predictionsPage(),
        activePredictionsFor: (_) {
          fetchCount++;
          return const ActivePredictionsPage(items: [], nextCursor: null);
        },
      );
      await tester.pumpWidget(_wrap(TrackingScreen(repository: repo)));
      await tester.pumpAndSettle();
      final initialCount = fetchCount;

      await tester.tap(find.text('30s'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 31));

      expect(fetchCount, greaterThan(initialCount));

      // Cancel the periodic timer before the test ends -- flutter_test
      // fails the test if a Timer is still pending at teardown.
      await tester.tap(find.text('Off'));
      await tester.pump();
    });
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/design_system.dart';
import 'package:mra_app/features/history/history_screen.dart';
import 'package:mra_app/features/tracking/tracked_prediction.dart';
import 'package:mra_app/features/tracking/tracking_filters.dart';
import 'package:mra_app/features/tracking/tracking_repository.dart';

/// EPIC-M3.17 — a minimal fake covering only [fetchPredictions] since
/// [HistoryScreen], unlike [TrackingScreen], never calls the other three
/// `/tracking/*` endpoints.
class _FakeTrackingRepository extends TrackingRepository {
  final List<TrackingFilters> filterCalls = [];
  final TrackedPredictionsPage Function(String? cursor) predictionsFor;

  _FakeTrackingRepository({required this.predictionsFor});

  @override
  Future<TrackedPredictionsPage> fetchPredictions({
    required String status,
    String? cursor,
    int pageSize = 10,
    TrackingFilters filters = const TrackingFilters(),
  }) async {
    expect(status, 'closed');
    filterCalls.add(filters);
    return predictionsFor(cursor);
  }
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

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

Finder _chip(String filterBarKey, String label) => find.descendant(
  of: find.byKey(Key(filterBarKey)),
  matching: find.text(label),
);

Finder _filtersButton() =>
    find.widgetWithIcon(OutlinedButton, Icons.filter_list);

void main() {
  testWidgets('renders the closed-predictions table from the real contract', (
    tester,
  ) async {
    final repo = _FakeTrackingRepository(
      predictionsFor: (_) => _predictionsPage(),
    );
    await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('History'), findsOneWidget);
    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets('shows an empty state when there are no closed predictions', (
    tester,
  ) async {
    final repo = _FakeTrackingRepository(
      predictionsFor: (_) =>
          const TrackedPredictionsPage(items: [], nextCursor: null),
    );
    await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('No closed predictions yet.'), findsOneWidget);
  });

  testWidgets('shows an error state and retries on demand', (tester) async {
    var attempt = 0;
    final repo = _FakeTrackingRepository(
      predictionsFor: (_) {
        attempt++;
        if (attempt == 1) throw Exception('boom');
        return _predictionsPage();
      },
    );
    await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets(
    'shows Load more when a next cursor exists and appends the next page',
    (tester) async {
      var page = 0;
      final repo = _FakeTrackingRepository(
        predictionsFor: (cursor) {
          page++;
          return page == 1
              ? _predictionsPage(nextCursor: 'cursor-2', id: 101)
              : _predictionsPage(nextCursor: null, id: 202);
        },
      );
      await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Load more'), findsOneWidget);

      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();

      expect(find.text('TATASTEEL'), findsNWidgets(2));
      expect(find.text('You’re all caught up'), findsOneWidget);
    },
  );

  testWidgets(
    'tapping a closed prediction pushes the recommendation detail route',
    (tester) async {
      final repo = _FakeTrackingRepository(
        predictionsFor: (_) => _predictionsPage(),
      );
      final router = GoRouter(
        routes: [
          GoRoute(
            path: '/history',
            builder: (context, state) =>
                Scaffold(body: HistoryScreen(repository: repo)),
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
        initialLocation: '/history',
      );

      await tester.pumpWidget(
        MaterialApp.router(theme: MraTheme.light(), routerConfig: router),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('TATASTEEL'));
      await tester.pumpAndSettle();

      expect(find.text('detail:101'), findsOneWidget);
    },
  );

  group('filters', () {
    testWidgets('Filters button shows the active filter count', (tester) async {
      final repo = _FakeTrackingRepository(
        predictionsFor: (_) => _predictionsPage(),
      );
      await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(_filtersButton(), findsOneWidget);

      await tester.tap(_filtersButton());
      await tester.pumpAndSettle();
      await tester.tap(_chip('trackingHorizonFilter', '3D'));
      await tester.pumpAndSettle();

      expect(
        find.widgetWithText(OutlinedButton, 'Filters (1)'),
        findsOneWidget,
      );
    });

    testWidgets('changing the horizon filter refetches with that horizon', (
      tester,
    ) async {
      final repo = _FakeTrackingRepository(
        predictionsFor: (_) => _predictionsPage(),
      );
      await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
      await tester.pumpAndSettle();

      await tester.tap(_filtersButton());
      await tester.pumpAndSettle();
      await tester.tap(_chip('trackingHorizonFilter', '5D'));
      await tester.pumpAndSettle();

      expect(repo.filterCalls.last.horizon, 5);
    });

    testWidgets('changing the regime filter refetches with that regime', (
      tester,
    ) async {
      final repo = _FakeTrackingRepository(
        predictionsFor: (_) => _predictionsPage(),
      );
      await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
      await tester.pumpAndSettle();

      await tester.tap(_filtersButton());
      await tester.pumpAndSettle();
      await tester.tap(_chip('trackingRegimeFilter', 'Bullish · high vol'));
      await tester.pumpAndSettle();

      expect(repo.filterCalls.last.regime, 'BULLISH_HIGH_VOL');
    });

    testWidgets('typing a symbol filter refetches with that symbol', (
      tester,
    ) async {
      final repo = _FakeTrackingRepository(
        predictionsFor: (_) => _predictionsPage(),
      );
      await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
      await tester.pumpAndSettle();

      await tester.tap(_filtersButton());
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'Symbol'), 'AAA');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      expect(repo.filterCalls.last.symbol, 'AAA');
    });

    testWidgets('Clear all filters resets to an empty filter set', (
      tester,
    ) async {
      final repo = _FakeTrackingRepository(
        predictionsFor: (_) => _predictionsPage(),
      );
      await tester.pumpWidget(_wrap(HistoryScreen(repository: repo)));
      await tester.pumpAndSettle();

      await tester.tap(_filtersButton());
      await tester.pumpAndSettle();
      await tester.tap(_chip('trackingHorizonFilter', '5D'));
      await tester.pumpAndSettle();
      expect(repo.filterCalls.last.isEmpty, false);

      await tester.tap(find.text('Clear all filters'));
      await tester.pumpAndSettle();

      expect(repo.filterCalls.last.isEmpty, true);
    });
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/dashboard_screen.dart';
import 'package:mra_app/features/dashboard/recommendation.dart';
import 'package:mra_app/features/dashboard/recommendations_repository.dart';

Map<String, dynamic> _item({
  int id = 1,
  String symbol = 'TATASTEEL',
  double? trustScore = 65,
  String evidenceFreshness = 'FRESH',
}) {
  return {
    'id': id,
    'symbol': symbol,
    'exchange': 'NSE',
    'companyName': 'Tata Steel Ltd.',
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
    'trustScore': trustScore?.toString(),
    'uncertaintyLevel': 'LOW',
    'fundamentalSummary': null,
    'newsSummary': null,
    'eventSummary': null,
    'marketSummary': null,
    'evidenceFreshness': evidenceFreshness,
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

class _FakeRepository extends RecommendationsRepository {
  final Future<RecommendationsPage> Function() onFetch;

  _FakeRepository(this.onFetch);

  @override
  Future<RecommendationsPage> fetchPage({
    int? horizonDays,
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

RecommendationsPage _pageOf(List<Map<String, dynamic>> raw, {String? next}) {
  return RecommendationsPage(
    items: raw.map(Recommendation.fromJson).toList(),
    nextCursor: next,
    asOfServerTime: DateTime.parse('2026-08-21T09:00:00Z'),
  );
}

void main() {
  testWidgets('shows skeleton loaders while the first page is in flight', (
    tester,
  ) async {
    final repo = _FakeRepository(
      () => Future.delayed(
        const Duration(milliseconds: 500),
        () => _pageOf([_item()]),
      ),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
    await tester.pump();

    expect(find.text('TATASTEEL'), findsNothing);
    await tester.pumpAndSettle();
    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets('renders recommendation cards and KPI strip on success', (
    tester,
  ) async {
    final repo = _FakeRepository(
      () async => _pageOf([_item(id: 1), _item(id: 2, symbol: 'INFY')]),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
    expect(find.text('INFY'), findsOneWidget);
    expect(find.text('Opportunities'), findsOneWidget);
    expect(find.text('2'), findsOneWidget); // opportunities count
  });

  testWidgets(
    'EPIC-M1.143: header and KPI strip survive 2x text scaling at compact '
    'width without overflow',
    (tester) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      final repo = _FakeRepository(() async => _pageOf([_item(id: 1)]));
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(
            size: Size(360, 800),
            textScaler: TextScaler.linear(2.0),
          ),
          child: _wrap(DashboardScreen(repository: repo)),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('shows an error state with retry on fetch failure', (
    tester,
  ) async {
    var attempts = 0;
    final repo = _FakeRepository(() async {
      attempts++;
      if (attempts == 1) {
        throw const ApiException(code: 'MRA_INTERNAL', message: 'Boom');
      }
      return _pageOf([_item()]);
    });
    await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Boom'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets('shows an empty state when zero recommendations are returned', (
    tester,
  ) async {
    final repo = _FakeRepository(() async => _pageOf(const []));
    await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.text('No positive opportunities match these filters.'),
      findsOneWidget,
    );
  });

  testWidgets('renders an explicit N/A trust indicator, not a fake score', (
    tester,
  ) async {
    final repo = _FakeRepository(
      () async => _pageOf([_item(trustScore: null)]),
    );
    await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('N/A'), findsOneWidget);
  });

  testWidgets(
    'EPIC-M1.144: a STALE evidenceFreshness renders a stale-evidence badge',
    (tester) async {
      final repo = _FakeRepository(
        () async => _pageOf([_item(evidenceFreshness: 'STALE')]),
      );
      await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Stale evidence'), findsOneWidget);
    },
  );

  testWidgets(
    'EPIC-M1.144: FRESH evidenceFreshness renders no stale-evidence badge',
    (tester) async {
      final repo = _FakeRepository(
        () async => _pageOf([_item(evidenceFreshness: 'FRESH')]),
      );
      await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Stale evidence'), findsNothing);
    },
  );

  testWidgets('tapping a card pushes the recommendation detail route', (
    tester,
  ) async {
    final repo = _FakeRepository(() async => _pageOf([_item(id: 42)]));
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/home',
          builder: (context, state) =>
              Scaffold(body: DashboardScreen(repository: repo)),
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
    'EPIC-M1.143: renders a realistic 100-item page without overflow or '
    'exceptions',
    (tester) async {
      final repo = _FakeRepository(
        () async =>
            _pageOf(List.generate(100, (i) => _item(id: i, symbol: 'SYM$i'))),
      );
      await tester.pumpWidget(_wrap(DashboardScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // First page's items render; scrolling further shouldn't be needed
      // to prove the large list itself laid out cleanly.
      expect(find.text('SYM0'), findsOneWidget);
    },
  );
}

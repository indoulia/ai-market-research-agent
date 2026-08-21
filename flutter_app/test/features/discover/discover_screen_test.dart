import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/recommendation.dart';
import 'package:mra_app/features/dashboard/recommendations_repository.dart';
import 'package:mra_app/features/discover/discover_screen.dart';
import 'package:mra_app/features/discover/discoveries_repository.dart';
import 'package:mra_app/features/discover/discovery_item.dart';

Map<String, dynamic> _rawItem({
  String symbol = 'TATASTEEL',
  String status = 'ISSUED',
  List<String> reasons = const ['52-week breakout'],
}) {
  return {
    'symbol': symbol,
    'companyName': 'Tata Steel Ltd.',
    'exchange': 'NSE',
    'sector': 'Materials',
    'industry': 'Steel',
    'marketCapBucket': 'LARGE_CAP',
    'liquidity': 'HIGH',
    'discoveredAt': '2026-08-20T09:00:00Z',
    'discoveryReasons': reasons,
    'score': '75',
    'trustScore': '70',
    'eligibility': true,
    'status': status,
  };
}

class _FakeDiscoveriesRepository extends DiscoveriesRepository {
  final Future<DiscoveriesPage> Function() onFetch;
  _FakeDiscoveriesRepository(this.onFetch);

  @override
  Future<DiscoveriesPage> fetchPage({
    String? market,
    String? sector,
    String? industry,
    String? marketCapBucket,
    String? liquidity,
    double? minScore,
    String sort = 'discoveredAt',
    bool descending = true,
    int pageSize = 20,
    String? cursor,
  }) => onFetch();
}

class _FakeRecommendationsRepository extends RecommendationsRepository {
  final int? matchId;
  _FakeRecommendationsRepository({this.matchId});

  @override
  Future<RecommendationsPage> fetchPage({
    int? horizonDays,
    RecommendationSort sort = RecommendationSort.score,
    bool descending = true,
    int pageSize = 20,
    String? cursor,
  }) async {
    return RecommendationsPage(
      items: matchId == null
          ? const []
          : [
              Recommendation.fromJson({
                'id': matchId,
                'symbol': 'TATASTEEL',
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
                'trustScore': '65',
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
              }),
            ],
      nextCursor: null,
      asOfServerTime: DateTime.parse('2026-08-21T09:00:00Z'),
    );
  }
}

Widget _wrapWithRouter(Widget child) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/discover',
        builder: (context, state) => Scaffold(body: child),
        routes: [
          GoRoute(
            path: 'recommendation/:id',
            builder: (context, state) =>
                Scaffold(body: Text('detail:${state.pathParameters['id']}')),
          ),
        ],
      ),
    ],
    initialLocation: '/discover',
  );
  return MaterialApp.router(theme: MraTheme.light(), routerConfig: router);
}

void main() {
  testWidgets('renders discovery cards with reason chips', (tester) async {
    final repo = _FakeDiscoveriesRepository(
      () async => DiscoveriesPage(
        items: [DiscoveryItem.fromJson(_rawItem())],
        nextCursor: null,
      ),
    );
    await tester.pumpWidget(_wrapWithRouter(DiscoverScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
    expect(find.text('52-week breakout'), findsOneWidget);
  });

  testWidgets('search filters the loaded list client-side', (tester) async {
    final repo = _FakeDiscoveriesRepository(
      () async => DiscoveriesPage(
        items: [
          DiscoveryItem.fromJson(_rawItem()),
          DiscoveryItem.fromJson(_rawItem(symbol: 'INFY')),
        ],
        nextCursor: null,
      ),
    );
    await tester.pumpWidget(_wrapWithRouter(DiscoverScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
    expect(find.text('INFY'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'INFY');
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsNothing);
    // "INFY" now matches both the search field's own input text and the
    // remaining card — findsWidgets, not findsOneWidget.
    expect(find.text('INFY'), findsWidgets);
  });

  testWidgets('shows an empty state when nothing is discovered', (
    tester,
  ) async {
    final repo = _FakeDiscoveriesRepository(
      () async => const DiscoveriesPage(items: [], nextCursor: null),
    );
    await tester.pumpWidget(_wrapWithRouter(DiscoverScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.text('No discovered candidates match these filters.'),
      findsOneWidget,
    );
  });

  testWidgets('tapping a card with a matching recommendation navigates', (
    tester,
  ) async {
    final repo = _FakeDiscoveriesRepository(
      () async => DiscoveriesPage(
        items: [DiscoveryItem.fromJson(_rawItem())],
        nextCursor: null,
      ),
    );
    await tester.pumpWidget(
      _wrapWithRouter(
        DiscoverScreen(
          repository: repo,
          recommendationsRepository: _FakeRecommendationsRepository(matchId: 7),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('TATASTEEL'));
    await tester.pumpAndSettle();

    expect(find.text('detail:7'), findsOneWidget);
  });

  testWidgets('tapping a card with no matching recommendation shows a toast', (
    tester,
  ) async {
    final repo = _FakeDiscoveriesRepository(
      () async => DiscoveriesPage(
        items: [DiscoveryItem.fromJson(_rawItem())],
        nextCursor: null,
      ),
    );
    await tester.pumpWidget(
      _wrapWithRouter(
        DiscoverScreen(
          repository: repo,
          recommendationsRepository: _FakeRecommendationsRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('TATASTEEL'));
    await tester.pumpAndSettle();

    expect(find.textContaining('No active recommendation'), findsOneWidget);
  });
}

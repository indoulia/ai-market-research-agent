import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/design_system/components/dense_data_table.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/recommendation.dart';
import 'package:mra_app/features/opportunities/opportunities_repository.dart';
import 'package:mra_app/features/opportunities/opportunity_explorer_screen.dart';

Map<String, dynamic> _item({
  int id = 1,
  String symbol = 'TATASTEEL',
  double? trustScore = 0.65,
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

class _RecordedCall {
  final String? market;
  final int? horizon;
  final String? sector;
  final String? industry;
  final String? marketCap;
  final double? minTrust;
  final String? liquidityBucket;
  final String? search;
  final OpportunitySort sort;
  final bool descending;
  final int page;

  _RecordedCall({
    required this.market,
    required this.horizon,
    required this.sector,
    required this.industry,
    required this.marketCap,
    required this.minTrust,
    required this.liquidityBucket,
    required this.search,
    required this.sort,
    required this.descending,
    required this.page,
  });
}

class _FakeRepository extends OpportunitiesRepository {
  final Future<OpportunitiesPage> Function(_RecordedCall call) onFetch;
  final List<_RecordedCall> calls = [];

  _FakeRepository(this.onFetch);

  @override
  Future<OpportunitiesPage> fetchPage({
    String? market,
    int? horizon,
    String? sector,
    String? industry,
    String? marketCap,
    double? minTrust,
    double? minScore,
    double? minUpside,
    String? liquidityBucket,
    String? status,
    String? search,
    OpportunitySort sort = OpportunitySort.score,
    bool descending = true,
    int page = 1,
    int pageSize = 20,
  }) {
    final call = _RecordedCall(
      market: market,
      horizon: horizon,
      sector: sector,
      industry: industry,
      marketCap: marketCap,
      minTrust: minTrust,
      liquidityBucket: liquidityBucket,
      search: search,
      sort: sort,
      descending: descending,
      page: page,
    );
    calls.add(call);
    return onFetch(call);
  }
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

OpportunitiesPage _pageOf(
  List<Map<String, dynamic>> raw, {
  int page = 1,
  int pageSize = 20,
  int? total,
}) {
  return OpportunitiesPage(
    items: raw.map(Recommendation.fromJson).toList(),
    page: page,
    pageSize: pageSize,
    total: total ?? raw.length,
    asOf: DateTime.parse('2026-08-21T09:00:00Z'),
  );
}

/// Some filter-chip labels ("Trust", "3D") coincide with unrelated text
/// rendered by [RecommendationCard]/[MraDenseTable] elsewhere on this
/// screen (e.g. `ScoreIndicator`'s "Trust" label, the dense table's
/// "Horizon" column). Scoping the finder to the specific keyed
/// [MraFilterBar] disambiguates it.
Finder _chip(String filterBarKey, String label) => find.descendant(
  of: find.byKey(Key(filterBarKey)),
  matching: find.text(label),
);

void main() {
  testWidgets('shows skeleton loaders while the first page is in flight', (
    tester,
  ) async {
    final repo = _FakeRepository(
      (_) => Future.delayed(
        const Duration(milliseconds: 500),
        () => _pageOf([_item()]),
      ),
    );
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pump();

    expect(find.text('TATASTEEL'), findsNothing);
    await tester.pumpAndSettle();
    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets('shows the result count and freshness once loaded', (
    tester,
  ) async {
    final repo = _FakeRepository(
      (_) async =>
          _pageOf([_item(id: 1), _item(id: 2, symbol: 'INFY')], total: 2),
    );
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('2 opportunities found'), findsOneWidget);
    expect(find.textContaining('As of'), findsOneWidget);
  });

  testWidgets('shows an empty state when zero opportunities match', (
    tester,
  ) async {
    final repo = _FakeRepository((_) async => _pageOf(const []));
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.text('No positive opportunities match these filters.'),
      findsOneWidget,
    );
  });

  testWidgets('shows an error state with retry on fetch failure', (
    tester,
  ) async {
    var attempts = 0;
    final repo = _FakeRepository((_) async {
      attempts++;
      if (attempts == 1) {
        throw const ApiException(code: 'MRA_INTERNAL', message: 'Boom');
      }
      return _pageOf([_item()]);
    });
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Boom'), findsOneWidget);

    await tester.ensureVisible(find.text('Retry'));
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
  });

  testWidgets(
    'renders a dense data table at wide (web) widths and cards at compact widths',
    (tester) async {
      final repoWide = _FakeRepository((_) async => _pageOf([_item()]));
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        _wrap(OpportunityExplorerScreen(repository: repoWide)),
      );
      await tester.pumpAndSettle();
      expect(find.text('Symbol'), findsOneWidget); // dense table header
      expect(find.text('Target / SL'), findsOneWidget); // dense table header
      expect(find.byType(MraDenseTable), findsOneWidget);

      tester.view.physicalSize = const Size(360, 800);
      await tester.pumpAndSettle();
      final repoCompact = _FakeRepository((_) async => _pageOf([_item()]));
      await tester.pumpWidget(
        _wrap(OpportunityExplorerScreen(repository: repoCompact)),
      );
      await tester.pumpAndSettle();
      expect(find.text('Symbol'), findsNothing);
      expect(find.byType(MraDenseTable), findsNothing);
    },
  );

  testWidgets('tapping an item pushes the recommendation detail route', (
    tester,
  ) async {
    final repo = _FakeRepository((_) async => _pageOf([_item(id: 42)]));
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/opportunities',
          builder: (context, state) =>
              Scaffold(body: OpportunityExplorerScreen(repository: repo)),
          routes: [
            GoRoute(
              path: 'recommendation/:id',
              builder: (context, state) =>
                  Scaffold(body: Text('detail:${state.pathParameters['id']}')),
            ),
          ],
        ),
      ],
      initialLocation: '/opportunities',
    );

    await tester.pumpWidget(
      MaterialApp.router(theme: MraTheme.light(), routerConfig: router),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('TATASTEEL'));
    await tester.pumpAndSettle();

    expect(find.text('detail:42'), findsOneWidget);
  });

  testWidgets('changing the horizon filter re-fetches with that horizon', (
    tester,
  ) async {
    final repo = _FakeRepository((_) async => _pageOf([_item()]));
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Filters'));
    await tester.pumpAndSettle();
    await tester.tap(_chip('opportunityHorizonFilter', '3D'));
    await tester.pumpAndSettle();

    expect(repo.calls.last.horizon, 3);
  });

  testWidgets('toggling a sort chip re-fetches sorted by that field', (
    tester,
  ) async {
    final repo = _FakeRepository((_) async => _pageOf([_item()]));
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Sort: Ranking'));
    await tester.pumpAndSettle();
    await tester.tap(_chip('opportunitySortFilter', 'Trust'));
    await tester.pumpAndSettle();

    expect(repo.calls.last.sort, OpportunitySort.trust);
    expect(repo.calls.last.descending, isTrue);
  });

  testWidgets('tapping the same sort chip again flips direction', (
    tester,
  ) async {
    final repo = _FakeRepository((_) async => _pageOf([_item()]));
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Sort: Ranking'));
    await tester.pumpAndSettle();
    await tester.tap(_chip('opportunitySortFilter', 'Ranking'));
    await tester.pumpAndSettle();

    expect(repo.calls.last.sort, OpportunitySort.ranking);
    expect(repo.calls.last.descending, isFalse);
  });

  testWidgets('typing in the search field re-fetches with the search term', (
    tester,
  ) async {
    final repo = _FakeRepository((_) async => _pageOf([_item()]));
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField).first, 'reli');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(repo.calls.last.search, 'reli');
  });

  testWidgets('changing the minimum-trust filter re-fetches with that floor', (
    tester,
  ) async {
    final repo = _FakeRepository((_) async => _pageOf([_item()]));
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Filters'));
    await tester.pumpAndSettle();
    await tester.tap(_chip('opportunityMinTrustFilter', '70%+'));
    await tester.pumpAndSettle();

    expect(repo.calls.last.minTrust, 0.7);
  });

  testWidgets('renders an explicit N/A trust cell, not a fabricated score', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final repo = _FakeRepository(
      (_) async => _pageOf([_item(trustScore: null)]),
    );
    await tester.pumpWidget(_wrap(OpportunityExplorerScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('N/A'), findsOneWidget);
  });
}

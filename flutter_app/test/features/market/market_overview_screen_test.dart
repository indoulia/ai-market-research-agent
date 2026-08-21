import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/market/market_overview_screen.dart';
import 'package:mra_app/features/market/market_repository.dart';
import 'package:mra_app/features/market/market_summary.dart';

class _FakeMarketRepository extends MarketRepository {
  final Future<MarketSummary> Function() onFetch;
  _FakeMarketRepository(this.onFetch);

  @override
  Future<MarketSummary> fetchSummary() => onFetch();
}

MarketSummary _summary({
  String marketStatus = 'OPEN',
  String? regime = 'BULLISH',
}) {
  return MarketSummary.fromJson({
    'asOf': '2026-08-21T09:00:00Z',
    'marketStatus': marketStatus,
    'regime': regime,
    'advanceDecline': '1.4',
    'volume': 1000000,
    'volatility': '12.5',
    'indexes': [],
    'sectorLeaders': [
      {'sector': 'IT', 'averageChangePct': '2.1'},
    ],
    'sectorLaggards': [
      {'sector': 'Energy', 'averageChangePct': '-1.3'},
    ],
  });
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('renders regime, breadth widgets and sector moves', (
    tester,
  ) async {
    final repo = _FakeMarketRepository(() async => _summary());
    await tester.pumpWidget(_wrap(MarketOverviewScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('BULLISH'), findsOneWidget);
    expect(find.text('Advance/Decline'), findsOneWidget);
    expect(find.textContaining('IT'), findsOneWidget);
    expect(find.textContaining('Energy'), findsOneWidget);
  });

  testWidgets('shows an honest placeholder when market status is unknown', (
    tester,
  ) async {
    final repo = _FakeMarketRepository(
      () async => _summary(marketStatus: 'UNKNOWN', regime: null),
    );
    await tester.pumpWidget(_wrap(MarketOverviewScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Status unavailable'), findsOneWidget);
    expect(find.text('Regime unavailable'), findsOneWidget);
  });

  testWidgets(
    'parses a populated indexes payload without throwing (contract regression)',
    (tester) async {
      // Found in the 2026-08-21 QA/integration audit: `indexes` was typed
      // List<String> while the API contract is List<IndexQuote> -- masked only
      // because the API always returned []. This proves real index objects
      // parse correctly now that the field/model shapes match.
      final repo = _FakeMarketRepository(
        () async => MarketSummary.fromJson({
          'asOf': '2026-08-21T09:00:00Z',
          'marketStatus': 'OPEN',
          'regime': 'BULLISH',
          'advanceDecline': '1.4',
          'volume': 1000000,
          'volatility': '12.5',
          'indexes': [
            {'name': 'NIFTY50', 'value': '19850.30', 'changePct': '0.42'},
          ],
          'sectorLeaders': [],
          'sectorLaggards': [],
        }),
      );

      await tester.pumpWidget(_wrap(MarketOverviewScreen(repository: repo)));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('1.40'), findsOneWidget); // advanceDecline now numeric
    },
  );
}

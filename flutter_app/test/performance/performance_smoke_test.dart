import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/dashboard/recommendation.dart';
import 'package:mra_app/features/opportunities/opportunities_repository.dart';
import 'package:mra_app/features/opportunities/opportunity_explorer_screen.dart';

/// EPIC-M3.14 — performance smoke tests.
///
/// No real device/profile-mode timeline (`flutter drive --profile` +
/// `integration_test`) is available in this environment — CI runs
/// `flutter test` only (`.github/workflows/flutter-ci.yml`), which has no
/// emulator/browser attached and always executes in debug-instrumented
/// mode, so a genuine jank/frame-budget measurement is not obtainable here.
/// This is a documented, deliberate scope reduction (see this EPIC's
/// Completion Report): a widget-test-level proxy that catches the two
/// regressions a real profiling run would also catch cheaply --
/// (1) a screen with a realistically large data set failing to build/settle
/// within a generous wall-clock budget (e.g. an accidental O(n^2) rebuild
/// loop), and (2) a scroll/fling over that data throwing or hanging.
class _FakeOpportunitiesRepository extends OpportunitiesRepository {
  final int itemCount;
  _FakeOpportunitiesRepository(this.itemCount);

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
  }) async {
    final items = List.generate(
      itemCount,
      (i) => Recommendation.fromJson(_item(i)),
    );
    return OpportunitiesPage(
      items: items,
      page: 1,
      pageSize: itemCount,
      total: itemCount,
      asOf: DateTime.parse('2026-08-21T09:00:00Z'),
    );
  }
}

Map<String, dynamic> _item(int i) => {
  'id': i,
  'symbol': 'SYM$i',
  'exchange': 'NSE',
  'companyName': 'Company $i Ltd.',
  'asOf': '2026-08-21T09:00:00Z',
  'price': '${100 + i}.00',
  'changePct': '1.0',
  'recommendation': 'POSITIVE_OPPORTUNITY',
  'horizonDays': 3,
  'targetPrice': '${110 + i}.00',
  'stopLoss': '${95 + i}.00',
  'upsidePct': '4.8',
  'probability': '0.7',
  'score': '80',
  'confidence': '70',
  'trustScore': '65',
  'uncertaintyLevel': 'LOW',
  'fundamentalSummary': null,
  'newsSummary': null,
  'eventSummary': null,
  'marketSummary': null,
  'evidenceFreshness': 'FRESH',
  'status': 'ISSUED',
  'predictionVersion': {'modelVersion': 'v1'},
  'updatedAt': '2026-08-21T09:00:00Z',
};

Widget _harness(Widget child) => MaterialApp(
  theme: MraTheme.light(),
  home: Scaffold(body: child),
);

void main() {
  testWidgets(
    'opportunity explorer with a large (200-item) result page builds and '
    'settles within a generous smoke-test budget',
    (tester) async {
      final stopwatch = Stopwatch()..start();
      await tester.pumpWidget(
        _harness(
          OpportunityExplorerScreen(
            repository: _FakeOpportunitiesRepository(200),
          ),
        ),
      );
      await tester.pumpAndSettle();
      stopwatch.stop();

      expect(find.text('SYM0'), findsWidgets);
      expect(tester.takeException(), isNull);
      // Generous smoke-test ceiling (real jank budgets are frame-level,
      // ~16ms/frame at 60fps) -- this only guards against a gross
      // regression (e.g. an accidental O(n^2) rebuild), not micro-jank.
      expect(
        stopwatch.elapsedMilliseconds,
        lessThan(10000),
        reason:
            'Opportunity Explorer took ${stopwatch.elapsedMilliseconds}ms '
            'to build/settle 200 items -- investigate for an accidental '
            'rebuild-per-item or O(n^2) regression.',
      );
    },
  );

  testWidgets(
    'flinging through a large opportunity list does not throw or hang',
    (tester) async {
      await tester.pumpWidget(
        _harness(
          OpportunityExplorerScreen(
            repository: _FakeOpportunitiesRepository(200),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.fling(
        find.byType(CustomScrollView),
        const Offset(0, -3000),
        4000,
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.fling(
        find.byType(CustomScrollView),
        const Offset(0, 3000),
        4000,
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );
}

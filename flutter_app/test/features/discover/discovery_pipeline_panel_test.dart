import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/discover/discoveries_repository.dart';
import 'package:mra_app/features/discover/discovery_history_point.dart';
import 'package:mra_app/features/discover/discovery_pipeline_panel.dart';
import 'package:mra_app/features/discover/discovery_summary.dart';

class _FakePipelineRepository extends DiscoveriesRepository {
  final DiscoverySummary? summary;
  final List<DiscoveryHistoryPoint> history;
  _FakePipelineRepository({this.summary, this.history = const []});

  @override
  Future<DiscoveriesPage> fetchPage({
    String? market,
    String? sector,
    String? industry,
    String? marketCapBucket,
    String? discoveryBasis,
    int pageSize = 20,
    String? cursor,
  }) async => const DiscoveriesPage(items: [], nextCursor: null);

  @override
  Future<DiscoverySummary> fetchSummary() async {
    final s = summary;
    if (s == null) throw StateError('no summary configured');
    return s;
  }

  @override
  Future<List<DiscoveryHistoryPoint>> fetchHistory({int days = 30}) async =>
      history;
}

Widget _wrap(Widget child) => MaterialApp(
  theme: MraTheme.light(),
  home: Scaffold(body: child),
);

void main() {
  testWidgets('renders funnel counts, timeline and effectiveness', (
    tester,
  ) async {
    final repo = _FakePipelineRepository(
      summary: DiscoverySummary(
        counts: const DiscoveryFunnelCounts(
          discovered: 12,
          analyzed: 9,
          qualified: 4,
          suppressed: 5,
          published: 2,
        ),
        effectivenessBySource: const [
          DiscoverySourceEffectiveness(
            source: 'CHATGPT',
            discoveredCount: 6,
            qualifiedCount: 3,
            successRate: 0.5,
            verdict: 'OK',
          ),
        ],
      ),
      history: [
        DiscoveryHistoryPoint(
          scanDate: DateTime(2027, 1, 1),
          discoveredCount: 3,
          analyzedCount: 3,
          qualifiedCount: 1,
          suppressedCount: 2,
          publishedCount: 0,
        ),
        DiscoveryHistoryPoint(
          scanDate: DateTime(2027, 1, 2),
          discoveredCount: 5,
          analyzedCount: 4,
          qualifiedCount: 2,
          suppressedCount: 2,
          publishedCount: 1,
        ),
      ],
    );

    await tester.pumpWidget(_wrap(DiscoveryPipelinePanel(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('12'), findsOneWidget);
    expect(find.text('Discovered'), findsOneWidget);
    expect(find.text('Analyzed'), findsOneWidget);
    expect(find.text('Qualified'), findsOneWidget);
    expect(find.text('Published'), findsOneWidget);
    expect(find.textContaining('CHATGPT'), findsOneWidget);
    expect(find.textContaining('50%'), findsOneWidget);
  });

  testWidgets('renders nothing when both requests fail', (tester) async {
    final repo = _FakePipelineRepository();

    await tester.pumpWidget(_wrap(DiscoveryPipelinePanel(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Discovered'), findsNothing);
  });
}

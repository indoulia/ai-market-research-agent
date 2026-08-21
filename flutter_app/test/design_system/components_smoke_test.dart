import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/design_system.dart';

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: Center(child: child)),
  );
}

void main() {
  group('MraCard', () {
    testWidgets('renders child and responds to tap', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        _wrap(
          MraCard(
            onTap: () => tapped = true,
            child: const Text('card content'),
          ),
        ),
      );
      expect(find.text('card content'), findsOneWidget);
      await tester.tap(find.text('card content'));
      expect(tapped, isTrue);
    });
  });

  group('KpiStatCard', () {
    testWidgets('shows label, value and delta', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const KpiStatCard(label: 'Opportunities', value: '18', delta: '+3'),
        ),
      );
      expect(find.text('Opportunities'), findsOneWidget);
      expect(find.text('18'), findsOneWidget);
      expect(find.text('+3'), findsOneWidget);
    });
  });

  group('MraChip', () {
    testWidgets('every tone renders its label', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const Wrap(
            children: [
              MraChip(label: 'Neutral', tone: MraChipTone.neutral),
              MraChip(label: 'Positive', tone: MraChipTone.positive),
              MraChip(label: 'Warning', tone: MraChipTone.warning),
              MraChip(label: 'Error', tone: MraChipTone.error),
              MraChip(label: 'Info', tone: MraChipTone.info),
            ],
          ),
        ),
      );
      for (final label in ['Neutral', 'Positive', 'Warning', 'Error', 'Info']) {
        expect(find.text(label), findsOneWidget);
      }
    });

    testWidgets('is tappable via Semantics button role', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        _wrap(MraChip(label: 'Tap me', onTap: () => tapped = true)),
      );
      await tester.tap(find.text('Tap me'));
      expect(tapped, isTrue);
    });
  });

  group('ScoreIndicator', () {
    testWidgets('renders rounded value and label for each kind', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const Row(
            children: [
              ScoreIndicator(kind: MraScoreKind.score, value0to100: 82),
              ScoreIndicator(kind: MraScoreKind.confidence, value0to100: 71),
              ScoreIndicator(kind: MraScoreKind.trust, value0to100: 65),
            ],
          ),
        ),
      );
      expect(find.text('82'), findsOneWidget);
      expect(find.text('Score'), findsOneWidget);
      expect(find.text('71'), findsOneWidget);
      expect(find.text('Confidence'), findsOneWidget);
      expect(find.text('65'), findsOneWidget);
      expect(find.text('Trust'), findsOneWidget);
    });

    testWidgets('clamps out-of-range values instead of crashing', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const ScoreIndicator(kind: MraScoreKind.score, value0to100: 140)),
      );
      expect(find.text('100'), findsOneWidget);
    });
  });

  group('TargetSlBadge', () {
    testWidgets('shows label text alongside price, not color alone', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const Column(
            children: [
              TargetSlBadge(
                kind: MraPriceBadgeKind.target,
                formattedPrice: '176.50',
              ),
              TargetSlBadge(
                kind: MraPriceBadgeKind.stopLoss,
                formattedPrice: '163.00',
              ),
            ],
          ),
        ),
      );
      expect(find.textContaining('Target'), findsOneWidget);
      expect(find.textContaining('Stop loss'), findsOneWidget);
      expect(find.textContaining('176.50'), findsOneWidget);
      expect(find.textContaining('163.00'), findsOneWidget);
    });

    testWidgets('EPIC-M1.143: exposes one combined semantics node per badge', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        _wrap(
          const TargetSlBadge(
            kind: MraPriceBadgeKind.target,
            formattedPrice: '176.50',
          ),
        ),
      );

      expect(find.bySemanticsLabel('Target 176.50'), findsOneWidget);
      handle.dispose();
    });
  });

  group('HorizonSelector', () {
    testWidgets('invokes onChanged with the tapped horizon', (tester) async {
      int? selected;
      await tester.pumpWidget(
        _wrap(
          StatefulBuilder(
            builder: (context, setState) => HorizonSelector(
              horizonsDays: const [1, 3, 5, 7],
              selectedDays: 3,
              onChanged: (v) => setState(() => selected = v),
            ),
          ),
        ),
      );
      await tester.tap(find.text('7D'));
      await tester.pump();
      expect(selected, 7);
    });
  });

  group('MraFilterBar', () {
    testWidgets('toggles selection on tap', (tester) async {
      final selectedIds = <String>{};
      await tester.pumpWidget(
        _wrap(
          SizedBox(
            width: 400,
            child: StatefulBuilder(
              builder: (context, setState) => MraFilterBar(
                options: const [MraFilterOption('a', 'Alpha')],
                selectedIds: selectedIds,
                onToggle: (id) => setState(() => selectedIds.add(id)),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Alpha'));
      await tester.pump();
      expect(selectedIds, contains('a'));
    });
  });

  group('MraDenseTable', () {
    testWidgets('renders header columns and row cells', (tester) async {
      await tester.pumpWidget(
        _wrap(
          MraDenseTable(
            columns: const [MraColumn('Symbol'), MraColumn('Price')],
            rows: [
              [const Text('TATASTEEL'), const Text('168.35')],
            ],
          ),
        ),
      );
      expect(find.text('Symbol'), findsOneWidget);
      expect(find.text('TATASTEEL'), findsOneWidget);
    });
  });

  group('RecommendationCard', () {
    testWidgets('renders symbol, price and score sections', (tester) async {
      await tester.pumpWidget(
        _wrap(
          RecommendationCard(
            data: RecommendationCardData(
              symbol: 'TATASTEEL',
              companyName: 'Tata Steel Ltd.',
              currentPrice: 168.35,
              changePercent: 1.42,
              horizonDays: 3,
              targetPrice: 176.5,
              stopLossPrice: 163.0,
              upsidePercent: 4.8,
              score: 82,
              confidence: 71,
              trust: 65,
              priceHistory: const [10.2, 10.6, 10.4, 10.9],
              lastUpdatedLabel: 'Updated 4m ago',
            ),
          ),
        ),
      );
      expect(find.text('TATASTEEL'), findsOneWidget);
      expect(find.text('Tata Steel Ltd.'), findsOneWidget);
      expect(find.textContaining('3D horizon'), findsOneWidget);
    });

    testWidgets(
      'renders honest placeholders when price/company/trust are absent',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            const RecommendationCard(
              data: RecommendationCardData(
                symbol: 'NEWCO',
                companyName: null,
                currentPrice: null,
                changePercent: null,
                horizonDays: 5,
                targetPrice: 100,
                stopLossPrice: 90,
                upsidePercent: 2.0,
                score: 50,
                confidence: 40,
                trust: null,
                priceHistory: [1, 2, 3],
                lastUpdatedLabel: 'Updated 1m ago',
              ),
            ),
          ),
        );

        expect(find.text('NEWCO'), findsOneWidget);
        expect(find.text('—'), findsOneWidget);
        expect(find.text('N/A'), findsOneWidget);
        expect(find.text('Trust'), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
  });

  group('NewsCard', () {
    testWidgets('renders headline, source and tag', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const NewsCard(
            headline: 'Headline text',
            source: 'Market Wire',
            publishedLabel: '2h ago',
            tag: 'Macro',
          ),
        ),
      );
      expect(find.text('Headline text'), findsOneWidget);
      expect(find.textContaining('Market Wire'), findsOneWidget);
      expect(find.text('Macro'), findsOneWidget);
    });
  });

  group('TimelineEventRow', () {
    testWidgets('renders title, subtitle and timestamp', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const TimelineEventRow(
            title: 'Recommendation generated',
            subtitle: 'Detail',
            timestampLabel: 'Aug 21, 09:15',
            isLast: true,
          ),
        ),
      );
      expect(find.text('Recommendation generated'), findsOneWidget);
      expect(find.text('Detail'), findsOneWidget);
      expect(find.text('Aug 21, 09:15'), findsOneWidget);
    });
  });

  group('SparklineChart', () {
    testWidgets('renders without values (edge case) and with values', (
      tester,
    ) async {
      await tester.pumpWidget(_wrap(const SparklineChart(values: [])));
      await tester.pumpWidget(_wrap(const SparklineChart(values: [1, 2, 3])));
      expect(tester.takeException(), isNull);
    });
  });

  group('SkeletonBox / SkeletonCard', () {
    testWidgets('renders without animation under reduced motion', (
      tester,
    ) async {
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: _wrap(const SkeletonCard()),
        ),
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('animates under normal motion settings', (tester) async {
      await tester.pumpWidget(_wrap(const SkeletonBox()));
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.takeException(), isNull);
    });
  });

  group('MraStateView', () {
    testWidgets('empty/error/offline factories render distinct titles', (
      tester,
    ) async {
      await tester.pumpWidget(_wrap(const MraStateView.empty()));
      expect(find.text('Nothing to show yet'), findsOneWidget);

      await tester.pumpWidget(_wrap(MraStateView.error(onAction: () {})));
      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      await tester.pumpWidget(_wrap(const MraStateView.offline()));
      expect(find.text("You're offline"), findsOneWidget);
    });
  });

  group('showMraToast', () {
    testWidgets('shows a snackbar with the message', (tester) async {
      await tester.pumpWidget(
        _wrap(
          Builder(
            builder: (context) => FilledButton(
              onPressed: () => showMraToast(context, 'Saved'),
              child: const Text('Trigger'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Trigger'));
      await tester.pump();
      expect(find.text('Saved'), findsOneWidget);
    });
  });

  group('showMraBottomSheet', () {
    testWidgets('opens a sheet with the given title and body', (tester) async {
      await tester.pumpWidget(
        _wrap(
          Builder(
            builder: (context) => FilledButton(
              onPressed: () => showMraBottomSheet(
                context: context,
                title: 'Sheet title',
                builder: (_) => const Text('Sheet body'),
              ),
              child: const Text('Open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      expect(find.text('Sheet title'), findsOneWidget);
      expect(find.text('Sheet body'), findsOneWidget);
    });
  });
}

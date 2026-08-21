import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/design_system.dart';

void main() {
  testWidgets('recommendation card survives 2x text scaling without overflow', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: MraTheme.light(),
        home: MediaQuery(
          data: const MediaQueryData(
            size: Size(400, 800),
            textScaler: TextScaler.linear(2.0),
          ),
          child: Scaffold(
            body: RecommendationCard(
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
        ),
      ),
    );

    // A RenderFlex overflow throws during layout; takeException() surfaces it.
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'MraBreakpoints classifies compact/medium/expanded/large widths',
    (tester) async {
      expect(MraBreakpoints.classify(400), MraWindowClass.compact);
      expect(MraBreakpoints.classify(800), MraWindowClass.medium);
      expect(MraBreakpoints.classify(1200), MraWindowClass.expanded);
      expect(MraBreakpoints.classify(1600), MraWindowClass.large);
    },
  );

  testWidgets('KPI grid does not overflow at narrow window widths', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: MraTheme.light(),
        home: MediaQuery(
          data: const MediaQueryData(size: Size(320, 640)),
          child: Scaffold(
            body: SizedBox(
              width: 320,
              child: Row(
                children: const [
                  Expanded(
                    child: KpiStatCard(label: 'Opportunities', value: '18'),
                  ),
                  Expanded(
                    child: KpiStatCard(label: 'Avg Trust', value: '76'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);
  });
}

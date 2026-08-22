import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/design_system.dart';
import 'package:mra_app/features/market/market_summary.dart';
import 'package:mra_app/features/market/sector_move_row.dart';

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: Center(child: child)),
  );
}

void main() {
  group('SectorMoveChip', () {
    testWidgets('an up move uses the market-up tone, not generic positive', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const SectorMoveChip(move: SectorMove('Energy', 1.4))),
      );
      final chip = tester.widget<MraChip>(find.byType(MraChip));
      expect(chip.tone, MraChipTone.marketUp);
    });

    testWidgets('a down move uses the market-down tone, not generic error', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const SectorMoveChip(move: SectorMove('Utilities', -0.8))),
      );
      final chip = tester.widget<MraChip>(find.byType(MraChip));
      expect(chip.tone, MraChipTone.marketDown);
    });
  });
}

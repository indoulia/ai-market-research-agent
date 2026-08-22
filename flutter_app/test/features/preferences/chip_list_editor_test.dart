import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/preferences/chip_list_editor.dart';

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets(
    'the add button has an accessible tooltip (EPIC-M3.13: an icon-only '
    'button must never be nameless)',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          ChipListEditor(
            label: 'Watchlist',
            hintText: 'Add symbol',
            values: const [],
            onChanged: (_) {},
          ),
        ),
      );

      expect(find.byTooltip('Add Watchlist'), findsOneWidget);
    },
  );

  testWidgets(
    'each chip exposes a per-item remove tooltip rather than a generic one',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          ChipListEditor(
            label: 'Watchlist',
            hintText: 'Add symbol',
            values: const ['TATASTEEL'],
            onChanged: (_) {},
          ),
        ),
      );

      expect(find.byTooltip('Remove TATASTEEL'), findsOneWidget);
    },
  );
}

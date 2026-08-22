import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/auth/splash_screen.dart';

void main() {
  testWidgets(
    'announces a label for screen readers instead of a silent spinner '
    '(EPIC-M3.13)',
    (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        MaterialApp(theme: MraTheme.light(), home: const SplashScreen()),
      );

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.bySemanticsLabel('Restoring your session'), findsOneWidget);
      handle.dispose();
    },
  );
}

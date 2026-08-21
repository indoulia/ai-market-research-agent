import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/preferences/preferences_settings_screen.dart';

void main() {
  testWidgets('shows both tabs and starts on Preferences', (tester) async {
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/settings',
          builder: (context, state) =>
              const Scaffold(body: PreferencesSettingsScreen()),
        ),
      ],
      initialLocation: '/settings',
    );
    await tester.pumpWidget(
      MaterialApp.router(theme: MraTheme.light(), routerConfig: router),
    );
    await tester.pumpAndSettle();

    expect(find.text('Preferences'), findsWidgets);
    expect(find.widgetWithText(Tab, 'Settings'), findsOneWidget);
    // No server in the test environment, so QuickPreferencesScreen (default
    // tab) lands on its error state rather than the loaded form.
    expect(find.text('Quick Preferences'), findsNothing);
  });

  testWidgets('switching to the Settings tab shows the gallery link', (
    tester,
  ) async {
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/settings',
          builder: (context, state) =>
              const Scaffold(body: PreferencesSettingsScreen()),
        ),
        GoRoute(
          path: '/dev/gallery',
          builder: (context, state) =>
              const Scaffold(body: Text('gallery placeholder')),
        ),
      ],
      initialLocation: '/settings',
    );
    await tester.pumpWidget(
      MaterialApp.router(theme: MraTheme.light(), routerConfig: router),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(Tab, 'Settings'));
    await tester.pumpAndSettle();

    expect(find.text('Design system gallery (QA)'), findsOneWidget);
  });
}

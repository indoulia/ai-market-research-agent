import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/app_shell/app_router.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';

Widget _appWithRouter(GoRouter router) {
  return MaterialApp.router(theme: MraTheme.light(), routerConfig: router);
}

void main() {
  testWidgets('compact width shows bottom navigation, not a rail', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_appWithRouter(buildAppRouter()));
    await tester.pumpAndSettle();

    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
  });

  testWidgets('wide width shows a navigation rail, not bottom navigation', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_appWithRouter(buildAppRouter()));
    await tester.pumpAndSettle();

    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });

  testWidgets('tapping a destination navigates and updates the route', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final router = buildAppRouter();
    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();

    expect(router.routerDelegate.currentConfiguration.uri.toString(), '/home');

    await tester.tap(find.text('Discover'));
    await tester.pumpAndSettle();

    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/discover',
    );
  });

  testWidgets('deep link to a recommendation detail route renders it', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final router = buildAppRouter();
    router.go('/home/recommendation/42');
    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();

    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/home/recommendation/42',
    );
    // The mocked test HttpClient returns 400, so the real detail screen
    // lands on its error state — proves the route resolved to the real
    // screen (EPIC-M1.138), not that data loaded (covered by that epic's
    // own repository-mocked tests).
    expect(find.text('Something went wrong'), findsOneWidget);
  });

  testWidgets('settings screen links to the design-system gallery', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final router = buildAppRouter();
    router.go('/settings');
    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();

    // The gallery link lives on the "Settings" tab, not the default
    // "Preferences" tab. The nav rail also has a "Settings" destination
    // label, so target the Tab widget specifically to avoid ambiguity.
    await tester.tap(find.widgetWithText(Tab, 'Settings'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Design system gallery (QA)'));
    await tester.pumpAndSettle();

    expect(find.text('MRA Design System Gallery'), findsOneWidget);
  });

  testWidgets('Alt+2 keyboard shortcut jumps to the Discover destination', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final router = buildAppRouter();
    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();

    await tester.sendKeyDownEvent(LogicalKeyboardKey.altLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.altLeft);
    await tester.pumpAndSettle();

    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/discover',
    );
  });

  testWidgets('switching branches and back preserves navigation state', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final router = buildAppRouter();
    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();

    router.go('/home/recommendation/7');
    await tester.pumpAndSettle();
    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/home/recommendation/7',
    );

    // Switch to another branch and back — the home branch's stack (still on
    // the recommendation detail route) must be preserved, not reset to
    // '/home'.
    router.go('/discover');
    await tester.pumpAndSettle();
    router.go('/home/recommendation/7');
    await tester.pumpAndSettle();
    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/home/recommendation/7',
    );
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/market/market_screen.dart';

void main() {
  testWidgets('switches between Overview and News & Events tabs', (
    tester,
  ) async {
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/market',
          builder: (context, state) => const Scaffold(body: MarketScreen()),
        ),
      ],
      initialLocation: '/market',
    );
    await tester.pumpWidget(
      MaterialApp.router(theme: MraTheme.light(), routerConfig: router),
    );
    await tester.pumpAndSettle();

    expect(find.text('Overview'), findsOneWidget);
    expect(find.text('News & Events'), findsOneWidget);

    await tester.tap(find.text('News & Events'));
    await tester.pumpAndSettle();

    // The symbol filter field only exists on the News & Events tab.
    expect(find.text('Filter by symbol'), findsOneWidget);
  });
}

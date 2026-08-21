import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/app_shell/app_router.dart';
import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/core/auth/auth_repository.dart';
import 'package:mra_app/core/auth/auth_session.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/detail/recommendation_detail_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

class _FakeAuthRepository extends AuthRepository {
  AuthSession? signInResult;

  @override
  Future<AuthSession> signIn(String userId) async => signInResult!;

  @override
  Future<bool> logout() async => true;
}

AuthSession _session() => AuthSession(
  sessionToken: 'tok-1',
  userId: 'analyst-1',
  issuedAt: DateTime.parse('2026-08-21T00:00:00Z'),
  expiresAt: DateTime.parse('2099-01-01T00:00:00Z'),
);

Widget _appWithRouter(GoRouter router) {
  return MaterialApp.router(theme: MraTheme.light(), routerConfig: router);
}

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  testWidgets('shows the splash screen while auth status is restoring', (
    tester,
  ) async {
    final controller = AuthController(repository: _FakeAuthRepository());
    final router = buildAppRouter(authController: controller);

    await tester.pumpWidget(_appWithRouter(router));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/splash',
    );
  });

  testWidgets(
    'unauthenticated redirects to sign-in, preserving the deep link',
    (tester) async {
      final controller = AuthController(repository: _FakeAuthRepository());
      await controller.restore();
      final router = buildAppRouter(authController: controller);
      router.go('/discover');

      await tester.pumpWidget(_appWithRouter(router));
      await tester.pumpAndSettle();

      expect(find.text('Sign in'), findsOneWidget);
      expect(
        router.routerDelegate.currentConfiguration.uri.toString(),
        '/sign-in?from=%2Fdiscover',
      );
    },
  );

  testWidgets('an expired session shows the session-expired banner', (
    tester,
  ) async {
    final prefs = SharedPreferencesAsync();
    await prefs.setString(
      'mra.auth_session.v1',
      '{"sessionToken":"tok","userId":"analyst-1",'
          '"issuedAt":"2026-08-21T00:00:00.000Z",'
          '"expiresAt":"2020-01-01T00:00:00.000Z"}',
    );
    final controller = AuthController(repository: _FakeAuthRepository());
    await controller.restore();
    final router = buildAppRouter(authController: controller);

    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();

    expect(find.textContaining('session expired'), findsOneWidget);
  });

  testWidgets('authenticated status renders the app shell, not sign-in', (
    tester,
  ) async {
    final repository = _FakeAuthRepository()..signInResult = _session();
    final controller = AuthController(repository: repository);
    await controller.signIn('analyst-1');
    final router = buildAppRouter(authController: controller);

    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();

    expect(find.text('Home'), findsWidgets);
    expect(router.routerDelegate.currentConfiguration.uri.toString(), '/home');
  });

  testWidgets('signing in navigates back to the originally requested path', (
    tester,
  ) async {
    final repository = _FakeAuthRepository()..signInResult = _session();
    final controller = AuthController(repository: repository);
    await controller.restore();
    final router = buildAppRouter(authController: controller);
    router.go('/discover');

    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();
    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/sign-in?from=%2Fdiscover',
    );

    await tester.enterText(find.byType(TextField), 'analyst-1');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(
      router.routerDelegate.currentConfiguration.uri.toString(),
      '/discover',
    );
  });

  testWidgets('signing out from Settings returns to sign-in', (tester) async {
    final repository = _FakeAuthRepository()..signInResult = _session();
    final controller = AuthController(repository: repository);
    await controller.signIn('analyst-1');
    final router = buildAppRouter(authController: controller);

    await tester.pumpWidget(_appWithRouter(router));
    await tester.pumpAndSettle();
    router.go('/settings');
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(Tab, 'Settings'));
    await tester.pumpAndSettle();

    expect(find.text('Signed in as analyst-1'), findsOneWidget);

    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();

    expect(find.text('Sign in'), findsOneWidget);
  });

  testWidgets(
    'EPIC-M1.144: a deep link straight into a nested recommendation route '
    'resolves that exact route/screen (simulates a web reload landing on '
    'the link, not just top-level tab navigation)',
    (tester) async {
      final repository = _FakeAuthRepository()..signInResult = _session();
      final controller = AuthController(repository: repository);
      await controller.signIn('analyst-1');
      // A fresh GoRouter with an `initialLocation` deep in a branch is
      // exactly what a real reload does: the app cold-starts and go_router
      // parses the URL from scratch, with no prior in-app navigation to
      // fall back on.
      final router = buildAppRouter(authController: controller);
      router.go('/home/recommendation/99');

      await tester.pumpWidget(_appWithRouter(router));
      await tester.pumpAndSettle();

      expect(
        router.routerDelegate.currentConfiguration.uri.toString(),
        '/home/recommendation/99',
      );
      final screen = tester.widget<RecommendationDetailScreen>(
        find.byType(RecommendationDetailScreen),
      );
      expect(screen.recommendationId, 99);
      // Not the dashboard/list — the deep link (not an auth redirect
      // default) drove which screen rendered.
      expect(find.text('Recommendations'), findsNothing);
    },
  );
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/core/auth/auth_repository.dart';
import 'package:mra_app/core/auth/auth_session.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/auth/sign_in_screen.dart';

class _FakeAuthRepository extends AuthRepository {
  AuthSession? signInResult;
  Object? signInError;

  @override
  Future<AuthSession> signIn(String userId) async {
    if (signInError != null) throw signInError!;
    return signInResult!;
  }
}

AuthSession _session() => AuthSession(
  sessionToken: 'tok-1',
  userId: 'analyst-1',
  issuedAt: DateTime.parse('2026-08-21T00:00:00Z'),
  expiresAt: DateTime.parse('2099-01-01T00:00:00Z'),
);

Widget _harness(Widget child) {
  return MaterialApp(theme: MraTheme.light(), home: child);
}

void main() {
  testWidgets('has no password field, only a User ID field', (tester) async {
    final controller = AuthController(repository: _FakeAuthRepository());

    await tester.pumpWidget(_harness(SignInScreen(controller: controller)));

    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('User ID'), findsOneWidget);
  });

  testWidgets('shows an error message when sign-in fails', (tester) async {
    final controller = AuthController(
      repository: _FakeAuthRepository()..signInError = Exception('boom'),
    );

    await tester.pumpWidget(_harness(SignInScreen(controller: controller)));
    await tester.enterText(find.byType(TextField), 'analyst-1');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(controller.lastError, isNotNull);
    expect(find.text(controller.lastError!), findsOneWidget);
  });

  testWidgets(
    'shows the session-expired banner when status is sessionExpired',
    (tester) async {
      final controller = AuthController(repository: _FakeAuthRepository())
        ..status = AuthStatus.sessionExpired;

      await tester.pumpWidget(_harness(SignInScreen(controller: controller)));

      expect(find.textContaining('session expired'), findsOneWidget);
    },
  );

  testWidgets('does nothing when submitting an empty user id', (tester) async {
    final repository = _FakeAuthRepository()..signInResult = _session();
    final controller = AuthController(repository: repository);

    await tester.pumpWidget(_harness(SignInScreen(controller: controller)));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(controller.status, isNot(AuthStatus.authenticated));
  });
}

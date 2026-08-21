import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/core/auth/auth_repository.dart';
import 'package:mra_app/core/auth/auth_session.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

class _FakeAuthRepository extends AuthRepository {
  AuthSession? signInResult;
  Object? signInError;
  bool logoutCalled = false;
  bool logoutThrows = false;

  @override
  Future<AuthSession> signIn(String userId) async {
    if (signInError != null) throw signInError!;
    return signInResult!;
  }

  @override
  Future<bool> logout() async {
    logoutCalled = true;
    if (logoutThrows) throw Exception('network down');
    return true;
  }
}

AuthSession _session({bool expired = false}) => AuthSession(
  sessionToken: 'tok-1',
  userId: 'analyst-1',
  issuedAt: DateTime.parse('2026-08-21T00:00:00Z'),
  expiresAt: expired
      ? DateTime.parse('2020-01-01T00:00:00Z')
      : DateTime.parse('2099-01-01T00:00:00Z'),
);

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    ApiClient.bearerToken = null;
  });

  tearDown(() {
    ApiClient.bearerToken = null;
  });

  test('restore with no stored session becomes unauthenticated', () async {
    final controller = AuthController(repository: _FakeAuthRepository());

    await controller.restore();

    expect(controller.status, AuthStatus.unauthenticated);
    expect(ApiClient.bearerToken, isNull);
  });

  test(
    'restore with a valid stored session becomes authenticated and sets the bearer token',
    () async {
      final prefs = SharedPreferencesAsync();
      await prefs.setString(
        'mra.auth_session.v1',
        '{"sessionToken":"tok-1","userId":"analyst-1","issuedAt":"2026-08-21T00:00:00.000Z","expiresAt":"2099-01-01T00:00:00.000Z"}',
      );
      final controller = AuthController(repository: _FakeAuthRepository());

      await controller.restore();

      expect(controller.status, AuthStatus.authenticated);
      expect(controller.session?.userId, 'analyst-1');
      expect(ApiClient.bearerToken, 'tok-1');
    },
  );

  test(
    'restore with an expired stored session becomes sessionExpired and clears the bearer token',
    () async {
      final prefs = SharedPreferencesAsync();
      await prefs.setString(
        'mra.auth_session.v1',
        '{"sessionToken":"tok-1","userId":"analyst-1","issuedAt":"2026-08-21T00:00:00.000Z","expiresAt":"2020-01-01T00:00:00.000Z"}',
      );
      final controller = AuthController(repository: _FakeAuthRepository());

      await controller.restore();

      expect(controller.status, AuthStatus.sessionExpired);
      expect(ApiClient.bearerToken, isNull);
    },
  );

  test('signIn success persists the session and sets authenticated', () async {
    final repository = _FakeAuthRepository()..signInResult = _session();
    final controller = AuthController(repository: repository);

    final ok = await controller.signIn('analyst-1');

    expect(ok, true);
    expect(controller.status, AuthStatus.authenticated);
    expect(ApiClient.bearerToken, 'tok-1');

    final prefs = SharedPreferencesAsync();
    expect(await prefs.getString('mra.auth_session.v1'), isNotNull);
  });

  test(
    'signIn failure records lastError and stays not-authenticated',
    () async {
      final repository = _FakeAuthRepository()..signInError = Exception('boom');
      final controller = AuthController(repository: repository);

      final ok = await controller.signIn('analyst-1');

      expect(ok, false);
      expect(controller.status, isNot(AuthStatus.authenticated));
      expect(controller.lastError, isNotNull);
    },
  );

  test('signOut clears local session even if the server call throws', () async {
    final repository = _FakeAuthRepository()
      ..signInResult = _session()
      ..logoutThrows = true;
    final controller = AuthController(repository: repository);
    await controller.signIn('analyst-1');

    await controller.signOut();

    expect(repository.logoutCalled, true);
    expect(controller.status, AuthStatus.unauthenticated);
    expect(controller.session, isNull);
    expect(ApiClient.bearerToken, isNull);
    final prefs = SharedPreferencesAsync();
    expect(await prefs.getString('mra.auth_session.v1'), isNull);
  });

  test('notifies listeners on status changes', () async {
    final controller = AuthController(repository: _FakeAuthRepository());
    var notifications = 0;
    controller.addListener(() => notifications++);

    await controller.restore();

    expect(notifications, greaterThanOrEqualTo(1));
  });

  test(
    'a mid-session MRA_SESSION_EXPIRED from any request flips status and clears the bearer token',
    () async {
      final repository = _FakeAuthRepository()..signInResult = _session();
      final controller = AuthController(repository: repository);
      await controller.signIn('analyst-1');
      expect(controller.status, AuthStatus.authenticated);

      ApiClient.onSessionExpired?.call();

      expect(controller.status, AuthStatus.sessionExpired);
      expect(ApiClient.bearerToken, isNull);
    },
  );

  test(
    'dispose unregisters the session-expired hook so it never fires on a disposed controller',
    () async {
      final controller = AuthController(repository: _FakeAuthRepository());
      expect(ApiClient.onSessionExpired, isNotNull);

      controller.dispose();

      expect(ApiClient.onSessionExpired, isNull);
    },
  );
}

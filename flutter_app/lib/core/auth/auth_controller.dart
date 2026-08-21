import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api_client.dart';
import '../api_exception.dart';
import 'auth_repository.dart';
import 'auth_session.dart';

/// EPIC-M1.146 — loading/authenticated/expired/unauthenticated states,
/// per this epic's own Scope ("Loading/authenticated/expired-session
/// states").
enum AuthStatus { restoring, authenticated, sessionExpired, unauthenticated }

const _storageKey = 'mra.auth_session.v1';

/// EPIC-M1.146 — app-wide auth state. A [ChangeNotifier] (not a bespoke
/// state-management library, matching this codebase's existing
/// StatefulWidget-only convention) so `go_router`'s `refreshListenable`
/// can react to sign-in/sign-out and the shell can gate routes.
///
/// Session restoration ("Sign-in/session restoration flow" — Scope) reads
/// a persisted token at startup via `shared_preferences` (a reasonable,
/// honest choice given the backend's own auth is currently a self-
/// asserted placeholder per M1.145's completion report — not pretending
/// to need bank-grade secure storage a placeholder auth doesn't warrant).
class AuthController extends ChangeNotifier {
  final AuthRepository _repository;
  final SharedPreferencesAsync? _injectedPrefs;
  SharedPreferencesAsync? _prefsInstance;

  AuthStatus status = AuthStatus.restoring;
  AuthSession? session;
  String? lastError;
  bool _disposed = false;
  late final void Function() _sessionExpiredHandler;

  AuthController({AuthRepository? repository, SharedPreferencesAsync? prefs})
    : _repository = repository ?? AuthRepository(),
      _injectedPrefs = prefs {
    // Catches a session that expires mid-session (any repository's request
    // can surface `MRA_SESSION_EXPIRED`), not just at cold-start `restore()`.
    _sessionExpiredHandler = _handleSessionExpiredMidSession;
    ApiClient.onSessionExpired = _sessionExpiredHandler;
  }

  // Lazy: a plain `AuthController()` that's pre-set to `authenticated` and
  // never has `restore()`/`signIn()`/`signOut()` called on it (the pattern
  // tests use to skip real session restoration) must not need a real
  // `SharedPreferencesAsyncPlatform` to have been registered.
  SharedPreferencesAsync get _prefs =>
      _prefsInstance ??= _injectedPrefs ?? SharedPreferencesAsync();

  void _handleSessionExpiredMidSession() {
    if (_disposed || status == AuthStatus.sessionExpired) return;
    status = AuthStatus.sessionExpired;
    ApiClient.bearerToken = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    if (ApiClient.onSessionExpired == _sessionExpiredHandler) {
      ApiClient.onSessionExpired = null;
    }
    super.dispose();
  }

  Future<void> restore() async {
    final raw = await _prefs.getString(_storageKey);
    if (raw == null) {
      status = AuthStatus.unauthenticated;
      notifyListeners();
      return;
    }
    final stored = AuthSession.fromJson(
      jsonDecode(raw) as Map<String, dynamic>,
    );
    if (stored.isExpired) {
      status = AuthStatus.sessionExpired;
      session = stored;
      ApiClient.bearerToken = null;
      notifyListeners();
      return;
    }
    ApiClient.bearerToken = stored.sessionToken;
    session = stored;
    status = AuthStatus.authenticated;
    notifyListeners();
  }

  Future<bool> signIn(String userId) async {
    try {
      final newSession = await _repository.signIn(userId);
      await _persist(newSession);
      lastError = null;
      status = AuthStatus.authenticated;
      notifyListeners();
      return true;
    } catch (e) {
      lastError = e is ApiException ? e.message : 'Sign-in failed.';
      notifyListeners();
      return false;
    }
  }

  Future<void> signOut() async {
    try {
      await _repository.logout();
    } catch (_) {
      // Best-effort server-side revoke; local state is cleared regardless
      // so the user is never stuck signed-in-looking on this device.
    }
    ApiClient.bearerToken = null;
    session = null;
    status = AuthStatus.unauthenticated;
    await _prefs.remove(_storageKey);
    notifyListeners();
  }

  Future<void> _persist(AuthSession newSession) async {
    session = newSession;
    ApiClient.bearerToken = newSession.sessionToken;
    await _prefs.setString(_storageKey, jsonEncode(newSession.toStorageJson()));
  }
}

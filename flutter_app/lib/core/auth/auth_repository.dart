import '../api_client.dart';
import 'auth_session.dart';

/// EPIC-M1.146 — repository boundary over the auth/session contract,
/// updated by EPIC-M3.12 to call the contract's explicit `login`/
/// `refresh`/`session`/`logout` verbs (EPIC-M1.145 originally shipped one
/// combined `POST /auth/session` endpoint for establish-or-refresh; M3.12
/// splits that into distinct endpoints — see `api/routers/auth.py`).
class AuthRepository {
  final ApiClient _client;

  AuthRepository({ApiClient? client}) : _client = client ?? ApiClient();

  /// Establishes a brand-new session for [userId] (this platform's
  /// backend is currently self-asserted — see M1.145's completion report
  /// — so there is no password to collect yet, only a user id).
  Future<AuthSession> signIn(String userId) async {
    final response = await _client.post(
      '/auth/login',
      body: {'userId': userId},
    );
    return AuthSession.fromJson(response.data as Map<String, dynamic>);
  }

  /// Refreshes/rotates the currently-set [ApiClient.bearerToken] session.
  /// Only meaningful when a *valid* (non-expired) token is already set —
  /// the server rejects a missing/invalid/expired token with a
  /// deterministic `MRA_UNAUTHENTICATED`/`MRA_SESSION_EXPIRED` error
  /// instead of silently minting a session for an unauthenticated caller.
  Future<AuthSession> refresh() async {
    final response = await _client.post('/auth/refresh', body: const {});
    return AuthSession.fromJson(response.data as Map<String, dynamic>);
  }

  /// Reads the caller's current session/user context from the server
  /// (`GET /auth/session`) without minting or rotating anything — the
  /// read-only counterpart to [signIn]/[refresh]. Exists for API-contract
  /// parity (EPIC-M3.12 names this endpoint explicitly); nothing calls it
  /// yet, matching this repository's own already-documented pattern of
  /// exposing the full contract even where nothing needs it today (see
  /// `refresh`'s honest gap note in EPIC-M1.146's completion report).
  Future<void> fetchSession() => _client.get('/auth/session');

  Future<bool> logout() async {
    final response = await _client.post('/auth/logout', body: const {});
    return (response.data as Map<String, dynamic>)['revoked'] as bool;
  }
}

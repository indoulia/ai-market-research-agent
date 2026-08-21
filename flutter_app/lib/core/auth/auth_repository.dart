import '../api_client.dart';
import 'auth_session.dart';

/// EPIC-M1.146 — repository boundary over EPIC-M1.145's real, merged
/// `/auth/session`, `/auth/logout`, `/me`, `/me/permissions` contracts.
class AuthRepository {
  final ApiClient _client;

  AuthRepository({ApiClient? client}) : _client = client ?? ApiClient();

  /// Establishes a brand-new session for [userId] (this platform's
  /// backend is currently self-asserted — see M1.145's completion report
  /// — so there is no password to collect yet, only a user id).
  Future<AuthSession> signIn(String userId) async {
    final response = await _client.post(
      '/auth/session',
      body: {'userId': userId},
    );
    return AuthSession.fromJson(response.data as Map<String, dynamic>);
  }

  /// Refreshes/rotates the currently-set [ApiClient.bearerToken] session.
  /// Only meaningful when a *valid* (non-expired) token is already set —
  /// the server falls through to requiring a fresh `signIn` otherwise
  /// (M1.145's own documented behavior, not something this client can
  /// paper over).
  Future<AuthSession> refresh() async {
    final response = await _client.post('/auth/session', body: const {});
    return AuthSession.fromJson(response.data as Map<String, dynamic>);
  }

  Future<bool> logout() async {
    final response = await _client.post('/auth/logout', body: const {});
    return (response.data as Map<String, dynamic>)['revoked'] as bool;
  }
}

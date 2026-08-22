import '../../core/api_client.dart';
import 'upstox_status.dart';

/// EPIC-MARKSY-0001 (fast-follow) — repository boundary over
/// `GET /api/v1/integrations/upstox/{authorize,status}`. Both routes
/// require an authenticated session server-side (`require_active_session`);
/// callers of this repository are expected to only render it once a real
/// session exists, same as the rest of this app's auth-gated repositories.
class UpstoxRepository {
  final ApiClient _client;

  UpstoxRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<UpstoxStatus> fetchStatus() async {
    final response = await _client.get('/integrations/upstox/status');
    return UpstoxStatus.fromJson(response.data as Map<String, dynamic>);
  }

  Future<UpstoxAuthorization> fetchAuthorization() async {
    final response = await _client.get('/integrations/upstox/authorize');
    return UpstoxAuthorization.fromJson(response.data as Map<String, dynamic>);
  }
}

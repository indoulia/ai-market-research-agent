import '../../core/api_client.dart';
import 'dashboard_snapshot.dart';

/// EPIC-M3.2 — repository boundary over `GET /api/v1/dashboard/snapshot`.
/// This is the dashboard's single "core content" request (AC): market
/// status/regime, top opportunities, important events, recent changes and
/// the trust summary all arrive together, so the Home screen's first paint
/// never needs more than one call.
class DashboardRepository {
  final ApiClient _client;

  DashboardRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<DashboardSnapshot> fetchSnapshot({
    String? market,
    int? horizonDays,
    String? sector,
    String? marketCapBucket,
    int limit = 10,
  }) async {
    final query = <String, String>{
      'limit': limit.toString(),
      'market': ?market,
      if (horizonDays != null) 'horizon': horizonDays.toString(),
      'sector': ?sector,
      'marketCapBucket': ?marketCapBucket,
    };
    final response = await _client.get('/dashboard/snapshot', query: query);
    return DashboardSnapshot.fromJson(response.data as Map<String, dynamic>);
  }
}

import '../../core/api_client.dart';
import 'market_summary.dart';

/// EPIC-M1.140 — repository boundary over EPIC-M1.139's
/// `GET /api/v1/market/summary`.
class MarketRepository {
  final ApiClient _client;

  MarketRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<MarketSummary> fetchSummary() async {
    final response = await _client.get('/market/summary');
    return MarketSummary.fromJson(response.data as Map<String, dynamic>);
  }
}

import '../../core/api_client.dart';
import 'preferences.dart';

/// EPIC-M1.142 — repository boundary over EPIC-M1.141's
/// `GET`/`PUT /api/v1/preferences`.
class PreferencesRepository {
  final ApiClient _client;

  PreferencesRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<Preferences> fetch() async {
    final response = await _client.get('/preferences');
    return Preferences.fromJson(response.data as Map<String, dynamic>);
  }

  Future<Preferences> update(Preferences preferences) async {
    final response = await _client.put(
      '/preferences',
      body: preferences.toJson(),
    );
    return Preferences.fromJson(response.data as Map<String, dynamic>);
  }
}

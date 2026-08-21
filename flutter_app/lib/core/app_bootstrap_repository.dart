import 'api_client.dart';

/// EPIC-M1.144 — parsed from EPIC-M1.132's real, merged
/// `GET /api/v1/app/bootstrap` (`api/schemas/bootstrap.py::BootstrapResponse`).
class AppBootstrapInfo {
  final String apiVersion;
  final String contractVersion;
  final Map<String, bool> capabilities;

  const AppBootstrapInfo({
    required this.apiVersion,
    required this.contractVersion,
    required this.capabilities,
  });

  factory AppBootstrapInfo.fromJson(Map<String, dynamic> json) {
    final rawCapabilities =
        (json['capabilities'] as Map<String, dynamic>?) ?? const {};
    return AppBootstrapInfo(
      apiVersion: json['apiVersion'] as String,
      contractVersion: json['contractVersion'] as String,
      capabilities: rawCapabilities.map(
        (key, value) => MapEntry(key, value as bool),
      ),
    );
  }
}

/// EPIC-M1.144 — repository boundary over `/app/bootstrap`, called once at
/// launch so the app can confirm it is speaking to a compatible server
/// contract before trusting anything else it fetches (see
/// `app_compatibility.dart`).
class AppBootstrapRepository {
  final ApiClient _client;

  AppBootstrapRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<AppBootstrapInfo> fetch() async {
    final response = await _client.get('/app/bootstrap');
    return AppBootstrapInfo.fromJson(response.data as Map<String, dynamic>);
  }
}

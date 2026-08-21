/// EPIC-M1.136 — API base URL, per EPIC-M1.132's `/api/{version}` namespace.
/// Overridable via `--dart-define=API_BASE_URL=...` for local/dev/staging
/// without a code change.
class ApiConfig {
  const ApiConfig._();

  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String apiV1 = '$baseUrl/api/v1';
}

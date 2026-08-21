import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'api_exception.dart';

/// EPIC-M1.136 — thin HTTP client for the `/api/v1` contract (EPIC-M1.132).
/// Decodes the success/error envelope; never invents payload shapes beyond
/// what the OpenAPI contract documents.
class ApiClient {
  final http.Client _http;

  ApiClient({http.Client? httpClient})
    : _http = httpClient ?? debugHttpClientOverride ?? http.Client();

  /// EPIC-M1.144 — test-only global transport override, mirroring the
  /// [bearerToken]/[onSessionExpired] "wire it centrally, not
  /// per-repository" pattern. Every repository/screen in this app builds a
  /// bare `ApiClient()` (never threading an [http.Client] through), so
  /// route-level end-to-end tests that exercise the real router/screens —
  /// not a screen-isolated fake repository — need one seam to redirect
  /// every one of those default clients at a single scripted transport.
  /// Must never be set outside a test; production code never touches this.
  static http.Client? debugHttpClientOverride;

  /// EPIC-M1.146 — the current session's bearer token, attached to every
  /// request as `Authorization: Bearer <token>` when set. A static field
  /// (not per-instance) so the many repositories that each construct their
  /// own `ApiClient()` all pick up sign-in/sign-out without being wired to
  /// an auth controller individually — set once, from one place
  /// (`AuthController`), per this repo's own "wire it centrally, not
  /// per-repository" note from EPIC-M1.142's completion report.
  static String? bearerToken;

  /// EPIC-M1.146 — called whenever a response carries `MRA_SESSION_EXPIRED`,
  /// wherever in the app that request happened to originate. Set once by
  /// [AuthController] so a session that expires mid-session (not just at
  /// cold-start `restore()`) still flips global auth state and the router
  /// redirects to sign-in — satisfying "expired sessions do not leave the
  /// user on a broken screen" without every repository/screen needing its
  /// own awareness of auth.
  static void Function()? onSessionExpired;

  Map<String, String> _headersWith(Map<String, String>? extra) => {
    if (bearerToken != null) 'Authorization': 'Bearer $bearerToken',
    ...?extra,
  };

  /// GETs `$apiV1$path` with [query], returning the decoded `data` value and
  /// leaving `meta` for the caller (cursor/page info lives there).
  Future<ApiResponse> get(String path, {Map<String, String>? query}) async {
    final uri = Uri.parse(
      '${ApiConfig.apiV1}$path',
    ).replace(queryParameters: query?.isEmpty ?? true ? null : query);
    final headers = _headersWith(null);
    return _decode(
      () => _http.get(uri, headers: headers.isEmpty ? null : headers),
    );
  }

  /// PUTs a JSON [body] to `$apiV1$path` (EPIC-M1.141's preference update).
  Future<ApiResponse> put(String path, {required Map<String, dynamic> body}) {
    final uri = Uri.parse('${ApiConfig.apiV1}$path');
    return _decode(
      () => _http.put(
        uri,
        headers: _headersWith(const {'Content-Type': 'application/json'}),
        body: jsonEncode(body),
      ),
    );
  }

  /// POSTs a JSON [body] to `$apiV1$path` (EPIC-M1.141's feedback
  /// submission). [headers] adds request-specific headers (e.g.
  /// `Idempotency-Key`) alongside `Content-Type`/`Authorization`.
  Future<ApiResponse> post(
    String path, {
    required Map<String, dynamic> body,
    Map<String, String>? headers,
  }) {
    final uri = Uri.parse('${ApiConfig.apiV1}$path');
    return _decode(
      () => _http.post(
        uri,
        headers: _headersWith({
          'Content-Type': 'application/json',
          ...?headers,
        }),
        body: jsonEncode(body),
      ),
    );
  }

  Future<ApiResponse> _decode(Future<http.Response> Function() send) async {
    http.Response response;
    try {
      response = await send();
    } catch (e) {
      throw ApiException.network(e);
    }

    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } catch (_) {
      throw ApiException(
        code: 'MRA_INTERNAL',
        message: 'The server returned an unreadable response.',
      );
    }

    if (response.statusCode >= 400) {
      final exception = ApiException.fromEnvelope(body);
      if (exception.code == 'MRA_SESSION_EXPIRED') {
        onSessionExpired?.call();
      }
      throw exception;
    }

    return ApiResponse(
      data: body['data'],
      meta: (body['meta'] as Map<String, dynamic>?) ?? const {},
    );
  }

  void close() => _http.close();
}

class ApiResponse {
  final dynamic data;
  final Map<String, dynamic> meta;

  const ApiResponse({required this.data, required this.meta});
}

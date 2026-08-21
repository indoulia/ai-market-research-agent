import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'api_exception.dart';

/// EPIC-M1.136 — thin HTTP client for the `/api/v1` contract (EPIC-M1.132).
/// Decodes the success/error envelope; never invents payload shapes beyond
/// what the OpenAPI contract documents.
class ApiClient {
  final http.Client _http;

  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  /// GETs `$apiV1$path` with [query], returning the decoded `data` value and
  /// leaving `meta` for the caller (cursor/page info lives there).
  Future<ApiResponse> get(String path, {Map<String, String>? query}) async {
    final uri = Uri.parse(
      '${ApiConfig.apiV1}$path',
    ).replace(queryParameters: query?.isEmpty ?? true ? null : query);
    return _decode(() => _http.get(uri));
  }

  /// PUTs a JSON [body] to `$apiV1$path` (EPIC-M1.141's preference update).
  Future<ApiResponse> put(String path, {required Map<String, dynamic> body}) {
    final uri = Uri.parse('${ApiConfig.apiV1}$path');
    return _decode(
      () => _http.put(
        uri,
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ),
    );
  }

  /// POSTs a JSON [body] to `$apiV1$path` (EPIC-M1.141's feedback
  /// submission). [headers] adds request-specific headers (e.g.
  /// `Idempotency-Key`) alongside `Content-Type`.
  Future<ApiResponse> post(
    String path, {
    required Map<String, dynamic> body,
    Map<String, String>? headers,
  }) {
    final uri = Uri.parse('${ApiConfig.apiV1}$path');
    return _decode(
      () => _http.post(
        uri,
        headers: {'Content-Type': 'application/json', ...?headers},
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
      throw ApiException.fromEnvelope(body);
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

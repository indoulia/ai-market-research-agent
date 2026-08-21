import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/core/auth/auth_repository.dart';

class _FakeHttpClient extends http.BaseClient {
  final int statusCode;
  final Object body;
  http.Request? lastRequest;

  _FakeHttpClient({required this.statusCode, required this.body});

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    lastRequest = request as http.Request;
    final encoded = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(Stream.value(encoded), statusCode);
  }
}

void main() {
  test('signIn posts userId and decodes the session', () async {
    final http_ = _FakeHttpClient(
      statusCode: 200,
      body: {
        'data': {
          'sessionToken': 'tok-1',
          'userId': 'analyst-1',
          'issuedAt': '2026-08-21T09:00:00Z',
          'expiresAt': '2026-08-21T21:00:00Z',
        },
        'meta': {'requestId': 'r1', 'timestamp': '2026-08-21T09:00:00Z'},
      },
    );
    final repository = AuthRepository(client: ApiClient(httpClient: http_));

    final session = await repository.signIn('analyst-1');

    expect(session.sessionToken, 'tok-1');
    expect(session.userId, 'analyst-1');
    expect(http_.lastRequest?.method, 'POST');
    expect(jsonDecode(http_.lastRequest!.body), {'userId': 'analyst-1'});
    expect(http_.lastRequest?.url.path, '/api/v1/auth/session');
  });

  test('logout posts and returns revoked', () async {
    final http_ = _FakeHttpClient(
      statusCode: 200,
      body: {
        'data': {'revoked': true},
        'meta': {'requestId': 'r2', 'timestamp': '2026-08-21T09:00:00Z'},
      },
    );
    final repository = AuthRepository(client: ApiClient(httpClient: http_));

    final revoked = await repository.logout();

    expect(revoked, true);
    expect(http_.lastRequest?.url.path, '/api/v1/auth/logout');
  });

  test('signIn throws ApiException on an error envelope', () async {
    final http_ = _FakeHttpClient(
      statusCode: 401,
      body: {
        'error': {
          'code': 'MRA_UNAUTHENTICATED',
          'message': 'Invalid session',
          'retryable': false,
        },
        'meta': {'requestId': 'r3', 'timestamp': '2026-08-21T09:00:00Z'},
      },
    );
    final repository = AuthRepository(client: ApiClient(httpClient: http_));

    await expectLater(
      repository.signIn('analyst-1'),
      throwsA(
        isA<ApiException>().having(
          (e) => e.code,
          'code',
          'MRA_UNAUTHENTICATED',
        ),
      ),
    );
  });
}

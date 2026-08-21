import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/core/api_exception.dart';

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
  test('get decodes the success envelope', () async {
    final http_ = _FakeHttpClient(
      statusCode: 200,
      body: {
        'data': {'symbol': 'TATASTEEL'},
        'meta': {'requestId': 'r1', 'timestamp': '2026-08-21T09:00:00Z'},
      },
    );
    final client = ApiClient(httpClient: http_);

    final response = await client.get('/recommendations/1');

    expect(response.data, {'symbol': 'TATASTEEL'});
    expect(response.meta['requestId'], 'r1');
  });

  test('get throws ApiException on an error envelope', () async {
    final http_ = _FakeHttpClient(
      statusCode: 404,
      body: {
        'error': {
          'code': 'MRA_NOT_FOUND',
          'message': 'Prediction was not found',
          'retryable': false,
        },
        'meta': {'requestId': 'r1', 'timestamp': '2026-08-21T09:00:00Z'},
      },
    );
    final client = ApiClient(httpClient: http_);

    await expectLater(
      client.get('/recommendations/999'),
      throwsA(
        isA<ApiException>()
            .having((e) => e.code, 'code', 'MRA_NOT_FOUND')
            .having((e) => e.retryable, 'retryable', false),
      ),
    );
  });

  test('put sends a JSON body and decodes the response', () async {
    final http_ = _FakeHttpClient(
      statusCode: 200,
      body: {
        'data': {'defaultHorizon': 5},
        'meta': {'requestId': 'r2', 'timestamp': '2026-08-21T09:00:00Z'},
      },
    );
    final client = ApiClient(httpClient: http_);

    final response = await client.put(
      '/preferences',
      body: {'defaultHorizon': 5},
    );

    expect(response.data, {'defaultHorizon': 5});
    expect(http_.lastRequest?.method, 'PUT');
    expect(jsonDecode(http_.lastRequest!.body), {'defaultHorizon': 5});
  });

  test('post sends a JSON body and decodes the response', () async {
    final http_ = _FakeHttpClient(
      statusCode: 200,
      body: {
        'data': {'feedbackId': 'f1', 'accepted': true},
        'meta': {'requestId': 'r3', 'timestamp': '2026-08-21T09:00:00Z'},
      },
    );
    final client = ApiClient(httpClient: http_);

    final response = await client.post(
      '/recommendations/1/feedback',
      body: {'type': 'useful'},
    );

    expect(response.data, {'feedbackId': 'f1', 'accepted': true});
    expect(http_.lastRequest?.method, 'POST');
  });
}

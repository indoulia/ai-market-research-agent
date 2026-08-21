import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/core/app_bootstrap_repository.dart';

class _FakeHttpClient extends http.BaseClient {
  final int statusCode;
  final Object body;
  _FakeHttpClient({required this.statusCode, required this.body});

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final encoded = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(Stream.value(encoded), statusCode);
  }
}

void main() {
  test('fetch parses apiVersion/contractVersion/capabilities', () async {
    final client = ApiClient(
      httpClient: _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': {
            'apiVersion': 'v1',
            'contractVersion': '2026-08-21',
            'serverTime': {'utc': '2026-08-22T00:00:00Z'},
            'capabilities': {
              'recommendations': true,
              'discovery': true,
              'auth': true,
            },
          },
          'meta': {'requestId': 'r1', 'timestamp': '2026-08-22T00:00:00Z'},
        },
      ),
    );
    final repository = AppBootstrapRepository(client: client);

    final info = await repository.fetch();

    expect(info.apiVersion, 'v1');
    expect(info.contractVersion, '2026-08-21');
    expect(info.capabilities['recommendations'], true);
    expect(info.capabilities['discovery'], true);
  });
}

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/features/tracking/tracking_repository.dart';

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
  test(
    'fetchSummary requests /tracking/summary with the given range',
    () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': {
            'range': '30d',
            'predictionCount': 5,
            'closedCount': 2,
            'targetHitRate': '0.5',
            'stopLossRate': '0.0',
            'horizonExpiryRate': '0.5',
            'avgRealizedReturn': '0.02',
            'avgPredictedReturn': '0.03',
            'calibrationScore': '0.1',
            'trustScore': '0.6',
            'trustDelta': null,
            'modelVersion': 'v1',
            'benchmarkReturn': null,
            'relativeReturn': null,
            'smallSample': true,
          },
          'meta': {'requestId': 'r1', 'timestamp': '2026-08-21T09:00:00Z'},
        },
      );
      final repository = TrackingRepository(
        client: ApiClient(httpClient: http_),
      );

      final summary = await repository.fetchSummary(range: '30d');

      expect(summary.predictionCount, 5);
      expect(summary.smallSample, true);
      expect(summary.activeCount, 3);
      expect(http_.lastRequest?.url.path, '/api/v1/tracking/summary');
      expect(http_.lastRequest?.url.queryParameters['range'], '30d');
    },
  );

  test(
    'fetchTimeseries requests /tracking/timeseries with metric/range/bucket',
    () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': {
            'metric': 'trust',
            'range': '30d',
            'bucket': 'day',
            'points': [
              {
                'bucketStart': '2026-08-01T00:00:00Z',
                'value': '0.5',
                'sampleCount': 3,
              },
            ],
          },
          'meta': {'requestId': 'r2', 'timestamp': '2026-08-21T09:00:00Z'},
        },
      );
      final repository = TrackingRepository(
        client: ApiClient(httpClient: http_),
      );

      final series = await repository.fetchTimeseries(
        metric: 'trust',
        range: '30d',
        bucket: 'day',
      );

      expect(series.points, hasLength(1));
      expect(series.points.first.value, 0.5);
      expect(http_.lastRequest?.url.queryParameters['metric'], 'trust');
      expect(http_.lastRequest?.url.queryParameters['bucket'], 'day');
    },
  );

  test(
    'fetchBreakdown requests /tracking/breakdown with the given dimension',
    () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': {
            'dimension': 'sector',
            'items': [
              {
                'key': 'IT',
                'predictionCount': 4,
                'closedCount': 2,
                'targetHitRate': '0.5',
                'avgRealizedReturn': '0.01',
                'smallSample': false,
              },
            ],
          },
          'meta': {'requestId': 'r3', 'timestamp': '2026-08-21T09:00:00Z'},
        },
      );
      final repository = TrackingRepository(
        client: ApiClient(httpClient: http_),
      );

      final breakdown = await repository.fetchBreakdown(dimension: 'sector');

      expect(breakdown.items.single.key, 'IT');
      expect(http_.lastRequest?.url.queryParameters['dimension'], 'sector');
    },
  );

  test(
    'fetchPredictions requests /tracking/predictions with status/cursor and decodes nextCursor',
    () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': [
            {
              'id': 7,
              'symbol': 'TATASTEEL',
              'status': 'closed',
              'asOf': '2026-08-01T00:00:00Z',
              'horizonDays': 5,
              'predictedReturn': '0.05',
              'realizedReturn': '0.03',
              'outcome': 'TARGET_HIT',
              'modelVersion': 'v1',
            },
          ],
          'meta': {
            'requestId': 'r4',
            'timestamp': '2026-08-21T09:00:00Z',
            'pageSize': 10,
            'nextCursor': 'abc',
          },
        },
      );
      final repository = TrackingRepository(
        client: ApiClient(httpClient: http_),
      );

      final page = await repository.fetchPredictions(
        status: 'closed',
        cursor: 'xyz',
      );

      expect(page.items.single.symbol, 'TATASTEEL');
      expect(page.nextCursor, 'abc');
      expect(http_.lastRequest?.url.queryParameters['status'], 'closed');
      expect(http_.lastRequest?.url.queryParameters['cursor'], 'xyz');
    },
  );
}

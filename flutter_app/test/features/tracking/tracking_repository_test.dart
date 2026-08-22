import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/features/tracking/tracking_filters.dart';
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

  // EPIC-M3.15: the from/to/horizon/sector/marketCap/regime/symbol/setup
  // filter surface this EPIC's API Contract names is forwarded as query
  // params on every fetch method.
  group('EPIC-M3.15 filters', () {
    final emptySummaryBody = {
      'data': {
        'range': 'custom',
        'predictionCount': 0,
        'closedCount': 0,
        'targetHitRate': null,
        'stopLossRate': null,
        'horizonExpiryRate': null,
        'avgRealizedReturn': null,
        'avgPredictedReturn': null,
        'calibrationScore': null,
        'trustScore': null,
        'trustDelta': null,
        'modelVersion': null,
        'benchmarkReturn': null,
        'relativeReturn': null,
        'smallSample': false,
      },
      'meta': {'requestId': 'r5', 'timestamp': '2026-08-21T09:00:00Z'},
    };

    test('fetchSummary forwards every filter as a query param', () async {
      final http_ = _FakeHttpClient(statusCode: 200, body: emptySummaryBody);
      final repository = TrackingRepository(
        client: ApiClient(httpClient: http_),
      );

      await repository.fetchSummary(
        range: '30d',
        filters: TrackingFilters(
          from: DateTime.utc(2026, 8, 1),
          to: DateTime.utc(2026, 8, 10),
          horizon: 5,
          sector: 'TECH',
          marketCap: 'LARGE_CAP',
          regime: 'BULLISH_LOW_VOL',
          symbol: 'AAA',
        ),
      );

      final query = http_.lastRequest!.url.queryParameters;
      expect(query['from'], DateTime.utc(2026, 8, 1).toIso8601String());
      expect(query['to'], DateTime.utc(2026, 8, 10).toIso8601String());
      expect(query['horizon'], '5');
      expect(query['sector'], 'TECH');
      expect(query['marketCap'], 'LARGE_CAP');
      expect(query['regime'], 'BULLISH_LOW_VOL');
      expect(query['symbol'], 'AAA');
    });

    test('fetchSummary omits filter query params when unset', () async {
      final http_ = _FakeHttpClient(statusCode: 200, body: emptySummaryBody);
      final repository = TrackingRepository(
        client: ApiClient(httpClient: http_),
      );

      await repository.fetchSummary(range: '30d');

      final query = http_.lastRequest!.url.queryParameters;
      expect(query.containsKey('horizon'), false);
      expect(query.containsKey('sector'), false);
      expect(query.containsKey('symbol'), false);
    });

    test('fetchPredictions forwards symbol/horizon filters', () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': [],
          'meta': {
            'requestId': 'r6',
            'timestamp': '2026-08-21T09:00:00Z',
            'pageSize': 10,
            'nextCursor': null,
          },
        },
      );
      final repository = TrackingRepository(
        client: ApiClient(httpClient: http_),
      );

      await repository.fetchPredictions(
        status: 'active',
        filters: const TrackingFilters(symbol: 'AAA', horizon: 3),
      );

      final query = http_.lastRequest!.url.queryParameters;
      expect(query['symbol'], 'AAA');
      expect(query['horizon'], '3');
    });
  });
}

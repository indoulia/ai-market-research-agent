import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/features/learning/learning_repository.dart';

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
    'fetchSummary requests /learning/summary and decodes the contract',
    () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': {
            'asOf': '2026-08-22T09:00:00Z',
            'currentModelVersion': 'model-v1',
            'lastCycle': null,
            'promotionCounts': {'promoted': 1, 'rejected': 0},
            'rollbackCount': 0,
            'latestRollback': null,
            'experimentCounts': {
              'total': 0,
              'ready': 0,
              'insufficientSample': 0,
              'pending': 0,
            },
            'failurePatternCount': 0,
            'recentSignals': [],
            'championChallenger': null,
            'methodologyVersion': 'LSI-001',
          },
          'meta': {'requestId': 'r1', 'timestamp': '2026-08-22T09:00:00Z'},
        },
      );
      final repository = LearningRepository(
        client: ApiClient(httpClient: http_),
      );

      final summary = await repository.fetchSummary();

      expect(summary.currentModelVersion, 'model-v1');
      expect(summary.promotionCounts.promoted, 1);
      expect(http_.lastRequest?.url.path, '/api/v1/learning/summary');
    },
  );

  test(
    'fetchHistory requests /learning/history with the given limit',
    () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': [
            {
              'id': 'cycle:1',
              'type': 'LEARNING_CYCLE',
              'createdAt': '2026-08-22T09:00:00Z',
              'status': 'RAN',
              'evidenceCount': 25,
              'methodologyVersion': 'CLC-001',
              'impact': 'Learning cycle evaluated 25 new outcome(s).',
              'modelVersion': null,
              'decisionReason': null,
            },
          ],
          'meta': {'requestId': 'r2', 'timestamp': '2026-08-22T09:00:00Z'},
        },
      );
      final repository = LearningRepository(
        client: ApiClient(httpClient: http_),
      );

      final history = await repository.fetchHistory(limit: 10);

      expect(history, hasLength(1));
      expect(history.single.type, 'LEARNING_CYCLE');
      expect(http_.lastRequest?.url.path, '/api/v1/learning/history');
      expect(http_.lastRequest?.url.queryParameters['limit'], '10');
    },
  );

  test(
    'fetchExperiments requests /learning/experiments and decodes arms',
    () async {
      final http_ = _FakeHttpClient(
        statusCode: 200,
        body: {
          'data': [
            {
              'id': 1,
              'name': 'feedback-target-too_high',
              'hypothesis': 'test hypothesis',
              'status': 'READY',
              'createdAt': '2026-08-22T09:00:00Z',
              'arms': [
                {
                  'armName': 'baseline',
                  'modelVersion': 'v1',
                  'windowLabel': 'w1',
                  'horizonDaysFilter': null,
                  'sampleCount': 25,
                  'accuracy': '0.55',
                  'verdict': 'READY',
                },
              ],
              'bestArmName': 'baseline',
              'feedbackDriven': true,
              'feedbackCategory': 'TARGET',
              'feedbackReasonCode': 'TOO_HIGH',
              'methodologyVersion': 'EXP-001',
            },
          ],
          'meta': {'requestId': 'r3', 'timestamp': '2026-08-22T09:00:00Z'},
        },
      );
      final repository = LearningRepository(
        client: ApiClient(httpClient: http_),
      );

      final experiments = await repository.fetchExperiments();

      expect(experiments, hasLength(1));
      expect(experiments.single.arms.single.accuracy, 0.55);
      expect(experiments.single.feedbackDriven, true);
      expect(http_.lastRequest?.url.path, '/api/v1/learning/experiments');
    },
  );
}

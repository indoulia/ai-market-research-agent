import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:mra_app/app_shell/app_router.dart';
import 'package:mra_app/core/api_client.dart';
import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

/// EPIC-M3.14 — the EPIC doc's Required Journey 5: "Home -> News/Event ->
/// affected prediction". Neither EPIC-M1.144's own e2e suite nor
/// `cross_screen_journeys_test.dart` (Explorer -> Detail) exercises the
/// Market destination's "News & Events" tab or
/// `findRecommendationIdBySymbol`'s symbol -> id lookup
/// (`lib/features/shared/recommendation_lookup.dart`) full-stack. Same
/// technique as the rest of this suite: only the HTTP transport is
/// scripted; real router, real screens, real repositories.
class _Resp {
  final int status;
  final Map<String, dynamic> body;
  const _Resp(this.status, this.body);
}

class _ScriptedHttpClient extends http.BaseClient {
  final List<http.Request> requests = [];
  final Map<String, _Resp Function(http.Request)> _handlers = {};

  void onStatic(String method, String path, _Resp response) =>
      _handlers['$method $path'] = (_) => response;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final req = request as http.Request;
    requests.add(req);
    final key = '${request.method} ${request.url.path}';
    final handler = _handlers[key];
    final resp =
        handler?.call(req) ??
        _Resp(404, {
          'error': {
            'code': 'MRA_NOT_FOUND',
            'message': 'no scripted handler for $key',
            'retryable': false,
          },
          'meta': {'requestId': 'unhandled', 'timestamp': _now},
        });
    final encoded = utf8.encode(jsonEncode(resp.body));
    return http.StreamedResponse(Stream.value(encoded), resp.status);
  }
}

const _now = '2026-08-22T09:00:00Z';

Map<String, dynamic> _envelope(
  dynamic data, [
  Map<String, dynamic> meta = const {},
]) => {
  'data': data,
  'meta': {'requestId': 'r1', 'timestamp': _now, ...meta},
};

final _authSessionJson = {
  'sessionToken': 'tok-e2e',
  'userId': 'analyst-1',
  'issuedAt': _now,
  'expiresAt': '2099-01-01T00:00:00Z',
};

final _emptyDashboardSnapshotJson = {
  'marketStatus': 'UNKNOWN',
  'asOf': _now,
  'marketRegime': null,
  'indices': [],
  'topOpportunities': [],
  'importantEvents': [],
  'recentChanges': [],
  'trustSummary': {
    'trustScore': null,
    'trustDelta': null,
    'calibrationScore': null,
    'sampleSize': 0,
    'smallSample': true,
    'modelVersion': null,
  },
  'dataFreshness': {
    'opportunitiesAsOf': _now,
    'marketAsOf': _now,
    'newsAsOf': null,
  },
};

final _marketSummaryJson = {
  'asOf': _now,
  'marketStatus': 'OPEN',
  'regime': null,
  'advanceDecline': null,
  'volume': null,
  'volatility': null,
  'indexes': <String>[],
  'sectorLeaders': <Map<String, dynamic>>[],
  'sectorLaggards': <Map<String, dynamic>>[],
};

final _newsItemJson = {
  'symbol': 'INFY',
  'headline': 'Infosys wins large multi-year outsourcing deal.',
  'source': 'Reuters',
  'publishedAt': _now,
  'detectedAt': _now,
  'materiality': 'HIGH',
  'eventType': 'NEWS_STORY',
  'affectedSecurities': <String>['INFY'],
  'evidenceId': 501,
};

Map<String, dynamic> _recommendationSummaryJson({
  int id = 55,
  String symbol = 'INFY',
}) => {
  'id': id,
  'symbol': symbol,
  'exchange': 'NSE',
  'companyName': 'Infosys Ltd.',
  'asOf': _now,
  'price': '1490.00',
  'changePct': '0.9',
  'recommendation': 'POSITIVE_OPPORTUNITY',
  'horizonDays': 5,
  'targetPrice': '1560.00',
  'stopLoss': '1450.00',
  'upsidePct': '4.7',
  'probability': '0.68',
  'score': '78',
  'confidence': '69',
  'trustScore': '72',
  'uncertaintyLevel': 'LOW',
  'fundamentalSummary': null,
  'newsSummary': null,
  'eventSummary': null,
  'marketSummary': null,
  'evidenceFreshness': 'FRESH',
  'status': 'ISSUED',
  'predictionVersion': {'modelVersion': 'v1'},
  'updatedAt': _now,
};

Map<String, dynamic> _detailJson({int id = 55, String symbol = 'INFY'}) => {
  'id': id,
  'symbol': symbol,
  'exchange': 'NSE',
  'companyName': 'Infosys Ltd.',
  'createdAt': _now,
  'updatedAt': _now,
  'asOf': _now,
  'entryPrice': '1470.00',
  'currentPrice': '1490.00',
  'targetPrice': '1560.00',
  'stopLoss': '1450.00',
  'horizonDays': 5,
  'expiryAt': null,
  'upsidePct': '4.7',
  'probability': '0.68',
  'score': '78',
  'confidence': '69',
  'trustScore': '72',
  'uncertainty': 'LOW',
  'evidenceStrength': 'STRONG',
  'fundamental': null,
  'technical': null,
  'market': null,
  'news': null,
  'events': null,
  'benchmarkRelative': null,
  'liquidity': 'HIGH',
  'providerEvidence': <String>['fundamental'],
  'status': 'ISSUED',
  'evidenceFreshness': 'FRESH',
  'predictionVersion': {'modelVersion': 'v1'},
};

final _initialTimelineJson = [
  {
    'version': 1,
    'timestamp': _now,
    'reason': 'INITIAL_PREDICTION',
    'changeSummary': 'Initial prediction issued.',
    'affectedMetrics': <String>[],
    'price': '1470.00',
    'targetPrice': '1560.00',
    'stopLoss': '1450.00',
    'probability': '0.68',
    'score': '78',
    'confidence': '69',
    'trustScore': '72',
  },
];

final _emptyOutcomeJson = {
  'status': 'PENDING',
  'detectedAt': null,
  'observedPrice': null,
  'realizedReturnPct': null,
  'targetHit': null,
  'stopLossHit': null,
  'horizonExpired': null,
  'benchmarkReturnPct': null,
  'evidenceId': null,
};

Widget _appWithRouter(GoRouter router) =>
    MaterialApp.router(theme: MraTheme.light(), routerConfig: router);

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  tearDown(() {
    ApiClient.debugHttpClientOverride = null;
    ApiClient.bearerToken = null;
    ApiClient.onSessionExpired = null;
  });

  testWidgets(
    'EPIC-M3.14 Required Journey 5: Home -> Market -> News & Events -> '
    'affected prediction, resolved via symbol lookup',
    (tester) async {
      final server = _ScriptedHttpClient();
      server.onStatic(
        'POST',
        '/api/v1/auth/login',
        _Resp(200, _envelope(_authSessionJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/dashboard/snapshot',
        _Resp(200, _envelope(_emptyDashboardSnapshotJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/market/summary',
        _Resp(200, _envelope(_marketSummaryJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/news',
        _Resp(200, _envelope([_newsItemJson])),
      );
      server.onStatic(
        'GET',
        '/api/v1/events',
        _Resp(200, _envelope(<Map<String, dynamic>>[])),
      );
      // findRecommendationIdBySymbol's client-side symbol -> id lookup.
      server.onStatic(
        'GET',
        '/api/v1/recommendations',
        _Resp(200, _envelope([_recommendationSummaryJson()])),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/55',
        _Resp(200, _envelope(_detailJson())),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/55/timeline',
        _Resp(200, _envelope(_initialTimelineJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/55/events',
        _Resp(200, _envelope(<Map<String, dynamic>>[])),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/55/outcome',
        _Resp(200, _envelope(_emptyOutcomeJson)),
      );
      ApiClient.debugHttpClientOverride = server;

      final authController = AuthController();
      await authController.restore();
      final router = buildAppRouter(authController: authController);
      await tester.pumpWidget(_appWithRouter(router));
      await tester.pumpAndSettle();

      // launch -> sign-in -> Home.
      await tester.enterText(find.byType(TextField), 'analyst-1');
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      // -> Market -> News & Events tab.
      router.go('/market');
      await tester.pumpAndSettle();
      await tester.tap(find.text('News & Events'));
      await tester.pumpAndSettle();

      expect(
        find.text('Infosys wins large multi-year outsourcing deal.'),
        findsOneWidget,
      );

      // -> tap the story: resolves INFY to id 55 via /recommendations, then
      // navigates to the affected recommendation's detail screen.
      await tester.tap(
        find.text('Infosys wins large multi-year outsourcing deal.'),
      );
      await tester.pumpAndSettle();

      expect(find.text('Infosys Ltd.'), findsOneWidget);
      expect(find.textContaining('Target 1560.00'), findsWidgets);

      final lookupRequest = server.requests.firstWhere(
        (r) => r.url.path == '/api/v1/recommendations',
      );
      expect(lookupRequest.url.queryParameters['pageSize'], '100');
      final detailRequest = server.requests.firstWhere(
        (r) => r.url.path == '/api/v1/recommendations/55',
      );
      expect(detailRequest.method, 'GET');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'EPIC-M3.14 Required Journey 5 failure path: no active recommendation '
    'for the symbol shows a toast instead of a broken/blank navigation',
    (tester) async {
      final server = _ScriptedHttpClient();
      server.onStatic(
        'POST',
        '/api/v1/auth/login',
        _Resp(200, _envelope(_authSessionJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/dashboard/snapshot',
        _Resp(200, _envelope(_emptyDashboardSnapshotJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/market/summary',
        _Resp(200, _envelope(_marketSummaryJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/news',
        _Resp(200, _envelope([_newsItemJson])),
      );
      server.onStatic(
        'GET',
        '/api/v1/events',
        _Resp(200, _envelope(<Map<String, dynamic>>[])),
      );
      // No matching recommendation for INFY -- the lookup returns empty.
      server.onStatic(
        'GET',
        '/api/v1/recommendations',
        _Resp(200, _envelope(<Map<String, dynamic>>[])),
      );
      ApiClient.debugHttpClientOverride = server;

      final authController = AuthController();
      await authController.restore();
      final router = buildAppRouter(authController: authController);
      await tester.pumpWidget(_appWithRouter(router));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'analyst-1');
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      router.go('/market');
      await tester.pumpAndSettle();
      await tester.tap(find.text('News & Events'));
      await tester.pumpAndSettle();

      await tester.tap(
        find.text('Infosys wins large multi-year outsourcing deal.'),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('No active recommendation for INFY yet.'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );
}

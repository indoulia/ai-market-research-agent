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

/// EPIC-M3.14 — full-stack coverage for the two Required Journeys
/// `flutter_app/test/e2e/end_to_end_journey_test.dart` (EPIC-M1.144) does
/// not touch: Journey 2 (Home -> Opportunity Explorer -> Detail) and a
/// genuine Journey 3 (Detail -> Prediction Timeline) exercised through a
/// real prediction *revision* (a target/SL state transition), not a
/// single-version payload. Same technique as M1.144's own suite: only the
/// HTTP transport is scripted (`ApiClient.debugHttpClientOverride`) — real
/// router, real screens, real repositories, driven the way a user would.
class _Resp {
  final int status;
  final Map<String, dynamic> body;
  const _Resp(this.status, this.body);
}

class _ScriptedHttpClient extends http.BaseClient {
  final List<http.Request> requests = [];
  final Map<String, _Resp Function(http.Request)> _handlers = {};

  void on(String method, String path, _Resp Function(http.Request) handler) {
    _handlers['$method $path'] = handler;
  }

  void onStatic(String method, String path, _Resp response) =>
      on(method, path, (_) => response);

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

Map<String, dynamic> _errorBody(
  String code,
  String message, {
  bool retryable = false,
}) => {
  'error': {'code': code, 'message': message, 'retryable': retryable},
  'meta': {'requestId': 'err1', 'timestamp': _now},
};

final _authSessionJson = {
  'sessionToken': 'tok-e2e',
  'userId': 'analyst-1',
  'issuedAt': _now,
  'expiresAt': '2099-01-01T00:00:00Z',
};

final _dashboardSnapshotEmptyJson = {
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

/// `DashboardOpportunity`'s deliberately leaner shape (EPIC-M3.2) — distinct
/// field names from the canonical `RecommendationSummary` contract
/// `_summaryJson` below models (`name` not `companyName`, `horizon` not
/// `horizonDays`, no evidence/provenance fields).
Map<String, dynamic> _dashboardOpportunityJson({
  int id = 77,
  String symbol = 'INFY',
}) => {
  'id': id,
  'symbol': symbol,
  'name': 'Infosys Ltd.',
  'price': '1490.00',
  'targetPrice': '1560.00',
  'stopLoss': '1450.00',
  'horizon': 5,
  'upsidePercent': '4.7',
  'score': '78',
  'confidence': '69',
  'trustScore': '72',
  'status': 'ISSUED',
  'updatedAt': _now,
};

/// The canonical recommendation-summary contract, shared verbatim by
/// `/opportunities`' `items[]` and `/recommendations` (EPIC-M3.3).
Map<String, dynamic> _summaryJson({int id = 77, String symbol = 'INFY'}) => {
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

Map<String, dynamic> _opportunitiesPageJson(List<Map<String, dynamic>> items) =>
    {
      'items': items,
      'page': 1,
      'pageSize': 20,
      'total': items.length,
      'asOf': _now,
      'filters': <String, dynamic>{},
    };

Map<String, dynamic> _detailJson({
  int id = 77,
  String symbol = 'INFY',
  String targetPrice = '1560.00',
  String stopLoss = '1450.00',
}) => {
  'id': id,
  'symbol': symbol,
  'exchange': 'NSE',
  'companyName': 'Infosys Ltd.',
  'createdAt': _now,
  'updatedAt': _now,
  'asOf': _now,
  'entryPrice': '1470.00',
  'currentPrice': '1490.00',
  'targetPrice': targetPrice,
  'stopLoss': stopLoss,
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
  'providerEvidence': ['fundamental'],
  'status': 'ISSUED',
  'evidenceFreshness': 'FRESH',
  'predictionVersion': {'modelVersion': 'v1'},
};

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

Finder _semanticsContaining(String text) =>
    find.bySemanticsLabel(RegExp(RegExp.escape(text)));

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
    'EPIC-M3.14 Required Journey 2: Login -> Home -> Opportunity Explorer '
    '-> Detail, with exact payload values carried through',
    (tester) async {
      final semanticsHandle = tester.ensureSemantics();
      final server = _ScriptedHttpClient();
      server.onStatic(
        'POST',
        '/api/v1/auth/login',
        _Resp(200, _envelope(_authSessionJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/dashboard/snapshot',
        _Resp(200, _envelope(_dashboardSnapshotEmptyJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/opportunities',
        _Resp(200, _envelope(_opportunitiesPageJson([_summaryJson()]))),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77',
        _Resp(200, _envelope(_detailJson())),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77/timeline',
        _Resp(
          200,
          _envelope([
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
          ]),
        ),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77/events',
        _Resp(200, _envelope(<Map<String, dynamic>>[])),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77/outcome',
        _Resp(200, _envelope(_emptyOutcomeJson)),
      );
      ApiClient.debugHttpClientOverride = server;

      final authController = AuthController();
      await authController.restore();
      final router = buildAppRouter(authController: authController);
      await tester.pumpWidget(_appWithRouter(router));
      await tester.pumpAndSettle();

      // launch -> unauthenticated -> sign-in.
      expect(find.text('Sign in'), findsOneWidget);
      await tester.enterText(find.byType(TextField), 'analyst-1');
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      // -> Home. The dashboard snapshot is intentionally empty here — this
      // journey is about Explorer -> Detail, not Home's own content.
      expect(
        find.text('No positive opportunities match these filters.'),
        findsOneWidget,
      );

      // -> Opportunity Explorer (direct navigation, matching this suite's
      // existing convention of `router.go` for cross-tab moves rather than
      // simulating a nav-rail/bottom-nav tap across breakpoints).
      router.go('/opportunities');
      await tester.pumpAndSettle();

      expect(find.text('INFY'), findsOneWidget);
      // The Explorer renders its dense table at this test's default 800x600
      // (medium) width — plain "target / SL" and trust cells, not
      // `RecommendationCard`'s semantics-labelled badges (asserted after the
      // drill-in below, where the same values render via the card-style
      // detail header).
      expect(find.text('1560.00 / 1450.00'), findsOneWidget);
      expect(find.text('72.00'), findsOneWidget);

      // -> Detail, via the Explorer's own drill-in route.
      await tester.tap(find.text('INFY'));
      await tester.pumpAndSettle();

      expect(find.text('Infosys Ltd.'), findsOneWidget);
      expect(_semanticsContaining('Target 1560.00'), findsOneWidget);
      expect(_semanticsContaining('Stop loss 1450.00'), findsOneWidget);
      expect(_semanticsContaining('Trust 72 out of 100'), findsOneWidget);

      final detailRequest = server.requests.firstWhere(
        (r) => r.url.path == '/api/v1/recommendations/77',
      );
      expect(detailRequest.method, 'GET');
      semanticsHandle.dispose();
    },
  );

  testWidgets('EPIC-M3.14 Required Journey 2 failure path: Explorer surfaces a '
      'retryable error, not stale/fabricated opportunities', (tester) async {
    final server = _ScriptedHttpClient();
    server.onStatic(
      'POST',
      '/api/v1/auth/login',
      _Resp(200, _envelope(_authSessionJson)),
    );
    server.onStatic(
      'GET',
      '/api/v1/dashboard/snapshot',
      _Resp(200, _envelope(_dashboardSnapshotEmptyJson)),
    );
    server.onStatic(
      'GET',
      '/api/v1/opportunities',
      _Resp(
        503,
        _errorBody(
          'MRA_PROVIDER_UNAVAILABLE',
          'The opportunities feed is temporarily unavailable.',
          retryable: true,
        ),
      ),
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

    router.go('/opportunities');
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(
      find.text('The opportunities feed is temporarily unavailable.'),
      findsOneWidget,
    );
    expect(find.text('Retry'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'EPIC-M3.14 Required Journey 3: Detail -> Prediction Timeline renders a '
    'real target/SL revision and the progressive-disclosure section '
    'collapses/expands in place',
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
        _Resp(
          200,
          _envelope({
            ..._dashboardSnapshotEmptyJson,
            'topOpportunities': [_dashboardOpportunityJson()],
            'recentChanges': [_dashboardOpportunityJson()],
          }),
        ),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77',
        _Resp(
          200,
          _envelope(_detailJson(targetPrice: '1560.00', stopLoss: '1450.00')),
        ),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77/timeline',
        _Resp(
          200,
          _envelope([
            {
              'version': 1,
              'timestamp': '2026-08-10T09:00:00Z',
              'reason': 'INITIAL_PREDICTION',
              'changeSummary': 'Initial prediction issued.',
              'affectedMetrics': <String>[],
              'price': '1470.00',
              'targetPrice': '1500.00',
              'stopLoss': '1460.00',
              'probability': '0.6',
              'score': '70',
              'confidence': '62',
              'trustScore': '68',
            },
            {
              'version': 2,
              'timestamp': _now,
              'reason': 'MATERIAL_EVIDENCE_CHANGE',
              'changeSummary':
                  'Target raised from 1500.00 to 1560.00 on stronger '
                  'quarterly guidance; stop-loss tightened.',
              'affectedMetrics': ['targetPrice', 'stopLoss'],
              'price': '1470.00',
              'targetPrice': '1560.00',
              'stopLoss': '1450.00',
              'probability': '0.68',
              'score': '78',
              'confidence': '69',
              'trustScore': '72',
            },
          ]),
        ),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77/events',
        _Resp(200, _envelope(<Map<String, dynamic>>[])),
      );
      server.onStatic(
        'GET',
        '/api/v1/recommendations/77/outcome',
        _Resp(200, _envelope(_emptyOutcomeJson)),
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

      // -> Home -> Detail.
      await tester.tap(find.text('INFY'));
      await tester.pumpAndSettle();

      // The above-the-fold "what changed" callout reads the *latest*
      // revision, proving the target/SL state transition surfaced, not
      // just the original prediction.
      await tester.ensureVisible(
        find.textContaining('Target raised from 1500.00 to 1560.00').first,
      );
      expect(
        find.textContaining('Target raised from 1500.00 to 1560.00'),
        findsWidgets,
      );
      expect(find.text('targetPrice'), findsOneWidget);
      expect(find.text('stopLoss'), findsOneWidget);

      // The full prediction-version timeline (progressive disclosure,
      // default-expanded) lists both versions in order.
      await tester.ensureVisible(
        find.text('Prediction-version timeline').first,
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('v1 · INITIAL_PREDICTION'), findsOneWidget);
      expect(
        find.textContaining('v2 · MATERIAL_EVIDENCE_CHANGE'),
        findsOneWidget,
      );

      // Collapse the section in place -> its entries disappear.
      await tester.tap(find.text('Prediction-version timeline').first);
      await tester.pumpAndSettle();
      expect(find.textContaining('v1 · INITIAL_PREDICTION'), findsNothing);
      expect(
        find.textContaining('v2 · MATERIAL_EVIDENCE_CHANGE'),
        findsNothing,
      );

      // Expand it again -> entries reappear, unchanged.
      await tester.tap(find.text('Prediction-version timeline').first);
      await tester.pumpAndSettle();
      expect(find.textContaining('v1 · INITIAL_PREDICTION'), findsOneWidget);
      expect(
        find.textContaining('v2 · MATERIAL_EVIDENCE_CHANGE'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );
}

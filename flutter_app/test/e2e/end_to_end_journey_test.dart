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

/// EPIC-M1.144 — end-to-end contract validation.
///
/// Every other Flutter test in this repo either fakes a *repository*
/// (screen-isolated) or fakes an *AuthRepository* (auth-isolated). Neither
/// proves the real app — real router, real screens, real repositories, all
/// built with a bare, un-injected default constructor exactly like
/// `main.dart` does — actually holds together end to end against one
/// consistently-scripted server. This file scripts only the HTTP
/// transport (`ApiClient.debugHttpClientOverride`, EPIC-M1.144) and drives
/// the app the same way a user would: type a user id, tap cards, tap
/// buttons, watch real navigation happen.
///
/// Covers the EPIC's named journey — launch -> recommendations -> detail
/// -> history -> event -> feedback -> preferences — plus its named failure
/// states (unauthorized, rate limited, timeout, server error, empty
/// result) at the same full-stack level.
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

Map<String, dynamic> _recommendationJson({
  int id = 42,
  String symbol = 'TATASTEEL',
  String evidenceFreshness = 'FRESH',
}) => {
  'id': id,
  'symbol': symbol,
  'exchange': 'NSE',
  'companyName': 'Tata Steel Ltd.',
  'asOf': _now,
  'price': '168.35',
  'changePct': '1.42',
  'recommendation': 'POSITIVE_OPPORTUNITY',
  'horizonDays': 3,
  'targetPrice': '176.50',
  'stopLoss': '163.00',
  'upsidePct': '4.8',
  'probability': '0.7',
  'score': '82',
  'confidence': '71',
  'trustScore': '65',
  'uncertaintyLevel': 'LOW',
  'fundamentalSummary': null,
  'newsSummary': null,
  'eventSummary': null,
  'marketSummary': null,
  'evidenceFreshness': evidenceFreshness,
  'status': 'ISSUED',
  'predictionVersion': {'modelVersion': 'v1'},
  'updatedAt': _now,
};

/// EPIC-M3.2 — the Home destination's initial "core content" request. One
/// opportunity mirroring [_recommendationJson]'s values so the existing
/// exact-value semantics assertions (target/SL/confidence/trust) still
/// hold against the leaner `DashboardOpportunity` shape.
Map<String, dynamic> _dashboardSnapshotJson({
  List<Map<String, dynamic>> topOpportunities = const [],
}) => {
  'marketStatus': 'UNKNOWN',
  'asOf': _now,
  'marketRegime': null,
  'indices': [],
  'topOpportunities': topOpportunities,
  'importantEvents': [],
  'recentChanges': topOpportunities,
  'trustSummary': {
    'trustScore': '0.7',
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

Map<String, dynamic> _opportunityJson({
  int id = 42,
  String symbol = 'TATASTEEL',
}) => {
  'id': id,
  'symbol': symbol,
  'name': 'Tata Steel Ltd.',
  'price': '168.35',
  'targetPrice': '176.50',
  'stopLoss': '163.00',
  'horizon': 3,
  'upsidePercent': '4.8',
  'score': '82',
  'confidence': '71',
  'trustScore': '65',
  'status': 'ISSUED',
  'updatedAt': _now,
};

final _detailPredictionVersion = {
  'modelVersion': 'v1',
  'featureVersion': '1',
  'consensusContractVersion': '1',
  'horizonSelectionVersion': '1',
  'scoringContractVersion': '1',
  'rankingVersion': '1',
};

Map<String, dynamic> _detailJson({int id = 42, String symbol = 'TATASTEEL'}) =>
    {
      'id': id,
      'symbol': symbol,
      'exchange': 'NSE',
      'companyName': 'Tata Steel Ltd.',
      'createdAt': _now,
      'updatedAt': _now,
      'asOf': _now,
      'entryPrice': '165.00',
      'currentPrice': '168.35',
      'targetPrice': '176.50',
      'stopLoss': '163.00',
      'horizonDays': 3,
      'expiryAt': null,
      'upsidePct': '4.8',
      'probability': '0.7',
      'score': '82',
      'confidence': '71',
      'trustScore': '65',
      'uncertainty': 'LOW',
      'evidenceStrength': 'STRONG',
      'fundamental': null,
      'technical': null,
      'market': null,
      'news': null,
      'events': null,
      'benchmarkRelative': null,
      'liquidity': 'HIGH',
      'providerEvidence': ['fundamental', 'technical'],
      'status': 'ISSUED',
      'predictionVersion': _detailPredictionVersion,
    };

final _historyJson = [
  {
    'timestamp': _now,
    'version': 1,
    'price': '165.00',
    'targetPrice': '176.50',
    'stopLoss': '163.00',
    'probability': '0.7',
    'score': '82',
    'confidence': '71',
    'trustScore': '65',
    'triggerType': 'INITIAL',
    'triggerEventId': null,
    'changeSummary': 'Initial prediction issued.',
  },
];

final _eventsJson = [
  {
    'timestamp': _now,
    'eventType': 'NEWS',
    'description': 'Quarterly results beat estimates.',
    'materiality': 'HIGH',
  },
];

final _outcomeJson = {
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

final _feedbackResultJson = {
  'feedbackId': 'fb-1',
  'accepted': true,
  'recordedAt': _now,
  'learningImpact': 'queued',
};

Map<String, dynamic> _preferencesJson({
  List<String> mutedAlertTypes = const [],
}) => {
  'defaultHorizon': 3,
  'markets': ['IN'],
  'sectors': [],
  'industries': [],
  'marketCapBuckets': [],
  'watchlist': [],
  'notificationPreferences': {'mutedAlertTypes': mutedAlertTypes},
  'displayPreferences': {
    'themeMode': 'system',
    'showFreshnessTimestamps': true,
  },
  'riskPreference': null,
  'minConfidenceThreshold': null,
  'preferenceVersion': 'v1',
};

/// Scripts the happy-path server for the full launch -> recommendations ->
/// detail -> history -> event -> feedback -> preferences journey.
_ScriptedHttpClient _happyPathServer() {
  final server = _ScriptedHttpClient();
  server.onStatic(
    'POST',
    '/api/v1/auth/session',
    _Resp(200, _envelope(_authSessionJson)),
  );
  server.onStatic(
    'GET',
    '/api/v1/recommendations',
    _Resp(200, _envelope([_recommendationJson()])),
  );
  server.onStatic(
    'GET',
    '/api/v1/dashboard/snapshot',
    _Resp(
      200,
      _envelope(_dashboardSnapshotJson(topOpportunities: [_opportunityJson()])),
    ),
  );
  server.onStatic(
    'GET',
    '/api/v1/recommendations/42',
    _Resp(200, _envelope(_detailJson())),
  );
  server.onStatic(
    'GET',
    '/api/v1/recommendations/42/history',
    _Resp(200, _envelope(_historyJson)),
  );
  server.onStatic(
    'GET',
    '/api/v1/recommendations/42/events',
    _Resp(200, _envelope(_eventsJson)),
  );
  server.onStatic(
    'GET',
    '/api/v1/recommendations/42/outcome',
    _Resp(200, _envelope(_outcomeJson)),
  );
  server.on(
    'POST',
    '/api/v1/recommendations/42/feedback',
    (_) => _Resp(200, _envelope(_feedbackResultJson)),
  );
  var preferences = _preferencesJson();
  server.on(
    'GET',
    '/api/v1/preferences',
    (_) => _Resp(200, _envelope(preferences)),
  );
  server.on('PUT', '/api/v1/preferences', (req) {
    final body = jsonDecode(req.body) as Map<String, dynamic>;
    preferences = _preferencesJson(
      mutedAlertTypes:
          ((body['notificationPreferences']
                      as Map<String, dynamic>)['mutedAlertTypes']
                  as List)
              .cast<String>(),
    );
    return _Resp(200, _envelope(preferences));
  });
  return server;
}

Widget _appWithRouter(GoRouter router) =>
    MaterialApp.router(theme: MraTheme.light(), routerConfig: router);

/// Matches a semantics node whose label *contains* [text], since a
/// tappable ancestor (e.g. `MraCard`) merges its descendants' individual
/// `Semantics(label: ...)` nodes into one combined label.
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

  testWidgets('EPIC-M1.144 happy path: sign-in -> recommendations -> detail '
      '(history+event) -> feedback -> preferences, with exact payload values', (
    tester,
  ) async {
    final semanticsHandle = tester.ensureSemantics();

    final server = _happyPathServer();
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

    // -> recommendations (dashboard).
    expect(find.text('TATASTEEL'), findsOneWidget);
    // Exact target/SL/trust/confidence values must match the payload, not
    // a reformatted/rounded guess. A tappable ancestor (`MraCard`'s
    // `InkWell`) merges each badge's own `Semantics(label: ...)` into one
    // combined node per card, so an exact `bySemanticsLabel` match no
    // longer applies — search the merged label for the same substring.
    expect(_semanticsContaining('Target 176.50'), findsOneWidget);
    expect(_semanticsContaining('Stop loss 163.00'), findsOneWidget);
    expect(_semanticsContaining('Confidence 71 out of 100'), findsOneWidget);
    expect(_semanticsContaining('Trust 65 out of 100'), findsOneWidget);

    // -> detail (+ history + event, fetched together per M1.138).
    await tester.tap(find.text('TATASTEEL'));
    await tester.pumpAndSettle();

    expect(_semanticsContaining('Target 176.50'), findsOneWidget);
    expect(_semanticsContaining('Stop loss 163.00'), findsOneWidget);
    expect(_semanticsContaining('Confidence 71 out of 100'), findsOneWidget);
    expect(_semanticsContaining('Trust 65 out of 100'), findsOneWidget);
    expect(
      find.text('Quarterly results beat estimates.'),
      findsOneWidget,
    ); // the event
    expect(find.textContaining('v1 · INITIAL'), findsOneWidget); // history

    // -> feedback. The detail screen is a long scrollable page — bring
    // the feedback section into the (small) test viewport first.
    await tester.ensureVisible(find.text('Useful'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Useful'));
    await tester.pumpAndSettle();

    expect(find.textContaining('queued for learning/analysis'), findsOneWidget);
    final feedbackRequest = server.requests.firstWhere(
      (r) => r.url.path == '/api/v1/recommendations/42/feedback',
    );
    final feedbackBody = jsonDecode(feedbackRequest.body) as Map;
    expect(feedbackBody['type'], 'useful');
    expect(feedbackBody['predictionVersion'], 'v1');

    // -> preferences: navigate to Settings and toggle a notification.
    router.go('/settings');
    await tester.pumpAndSettle();

    expect(find.text('Prediction expiry'), findsOneWidget);
    await tester.ensureVisible(find.text('Prediction expiry'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Prediction expiry'));
    await tester.pumpAndSettle();

    final putRequest = server.requests.lastWhere(
      (r) => r.method == 'PUT' && r.url.path == '/api/v1/preferences',
    );
    final putBody = jsonDecode(putRequest.body) as Map;
    expect(
      (putBody['notificationPreferences'] as Map)['mutedAlertTypes'],
      contains('EXPIRY'),
    );
    expect(find.text('Saved'), findsOneWidget);
    semanticsHandle.dispose();
  });

  testWidgets(
    'EPIC-M1.144 failure path: unauthorized (session expired) redirects to '
    'sign-in instead of showing stale data',
    (tester) async {
      final server = _ScriptedHttpClient();
      server.onStatic(
        'POST',
        '/api/v1/auth/session',
        _Resp(200, _envelope(_authSessionJson)),
      );
      server.onStatic(
        'GET',
        '/api/v1/dashboard/snapshot',
        _Resp(
          401,
          _errorBody('MRA_SESSION_EXPIRED', 'Your session has expired.'),
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

      // The dashboard's own fetch surfaces MRA_SESSION_EXPIRED, which
      // ApiClient.onSessionExpired routes into a global session-expired
      // redirect — not a screen-local error banner showing stale data.
      expect(find.textContaining('session expired'), findsOneWidget);
    },
  );

  testWidgets('EPIC-M1.144 failure path: rate limited shows a retryable error, '
      'network timeout shows a retryable network error', (tester) async {
    final server = _ScriptedHttpClient();
    server.onStatic(
      'POST',
      '/api/v1/auth/session',
      _Resp(200, _envelope(_authSessionJson)),
    );
    server.onStatic(
      'GET',
      '/api/v1/dashboard/snapshot',
      _Resp(
        429,
        _errorBody(
          'MRA_RATE_LIMITED',
          'Too many requests. Please retry later.',
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

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Too many requests. Please retry later.'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets(
    'EPIC-M1.144 failure path: server error (5xx) on detail shows an error '
    'state with retry, not a crash or fabricated data',
    (tester) async {
      final server = _happyPathServer();
      server.onStatic(
        'GET',
        '/api/v1/recommendations/42',
        _Resp(500, _errorBody('MRA_INTERNAL', 'Boom.', retryable: true)),
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

      await tester.tap(find.text('TATASTEEL'));
      await tester.pumpAndSettle();

      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.text('Boom.'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'EPIC-M1.144 failure path: empty recommendations result renders an '
    'explicit empty state, not a blank/loading screen forever',
    (tester) async {
      final server = _happyPathServer();
      server.onStatic(
        'GET',
        '/api/v1/dashboard/snapshot',
        _Resp(200, _envelope(_dashboardSnapshotJson())),
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

      expect(
        find.text('No positive opportunities match these filters.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'EPIC-M1.144 failure path: a transport-level network failure (server '
    'unreachable/timeout) surfaces the network error, not a crash',
    (tester) async {
      final server = _ScriptedHttpClient();
      server.onStatic(
        'POST',
        '/api/v1/auth/session',
        _Resp(200, _envelope(_authSessionJson)),
      );
      server.on('GET', '/api/v1/dashboard/snapshot', (_) {
        throw const SocketExceptionStub('provider unavailable');
      });
      ApiClient.debugHttpClientOverride = server;

      final authController = AuthController();
      await authController.restore();
      final router = buildAppRouter(authController: authController);
      await tester.pumpWidget(_appWithRouter(router));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'analyst-1');
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.text('Could not reach the server.'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}

/// A minimal stand-in for a real transport exception (e.g. `SocketException`
/// from `dart:io`, unavailable on web) — [ApiClient] catches `Object`, not a
/// specific exception type, so any thrown object exercises the same path.
class SocketExceptionStub implements Exception {
  final String message;
  const SocketExceptionStub(this.message);
  @override
  String toString() => 'SocketExceptionStub: $message';
}

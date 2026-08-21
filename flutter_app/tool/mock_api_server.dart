// EPIC-M1.144 — a real, standalone `/api/v1` mock server for Flutter UI
// development, so a UI change can be built/reviewed without a running
// Python backend or database. Dev-only: it is a `tool/` script, never
// imported by `lib/`, so it cannot end up in a shipped build; the app
// still only ever calls the real API in production (Scope: "UI never
// silently falls back to stale fixture data in production builds" is
// enforced by that separation, not by anything in this file).
//
// Run:
//   dart run tool/mock_api_server.dart [port]
// Then point the app at it:
//   flutter run --dart-define=API_BASE_URL=http://localhost:8090
//
// Every response uses the same envelope/error shape as the real API
// (`docs/api/VERSIONING.md`) and the same field names as
// `docs/api/openapi.json`, so it exercises the app's real parsing code —
// this is fixture *data* behind the real contract, not a fake contract.
library;

import 'dart:convert';
import 'dart:io';

const _contractVersion = '2026-08-21';

String _nowIso() => DateTime.now().toUtc().toIso8601String();

Map<String, dynamic> _envelope(
  dynamic data, [
  Map<String, dynamic>? extraMeta,
]) => {
  'data': data,
  'meta': {
    'requestId': 'mock-${DateTime.now().microsecondsSinceEpoch}',
    'timestamp': _nowIso(),
    ...?extraMeta,
  },
};

Map<String, dynamic> _recommendation({
  required int id,
  required String symbol,
  required String companyName,
  required String price,
  required String targetPrice,
  required String stopLoss,
  String evidenceFreshness = 'FRESH',
}) => {
  'id': id,
  'symbol': symbol,
  'exchange': 'NSE',
  'companyName': companyName,
  'asOf': _nowIso(),
  'price': price,
  'changePct': '1.42',
  'recommendation': 'POSITIVE_OPPORTUNITY',
  'horizonDays': 3,
  'targetPrice': targetPrice,
  'stopLoss': stopLoss,
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
  'predictionVersion': {
    'modelVersion': 'mock-1',
    'featureVersion': '1',
    'consensusContractVersion': '1',
    'horizonSelectionVersion': '1',
    'scoringContractVersion': '1',
    'rankingVersion': '1',
  },
  'updatedAt': _nowIso(),
};

final _recommendations = [
  _recommendation(
    id: 1,
    symbol: 'TATASTEEL',
    companyName: 'Tata Steel Ltd.',
    price: '168.35',
    targetPrice: '176.50',
    stopLoss: '163.00',
  ),
  _recommendation(
    id: 2,
    symbol: 'INFY',
    companyName: 'Infosys Ltd.',
    price: '1520.10',
    targetPrice: '1600.00',
    stopLoss: '1470.00',
    evidenceFreshness: 'STALE',
  ),
];

Map<String, dynamic> _detailFor(int id) {
  final summary = _recommendations.firstWhere(
    (r) => r['id'] == id,
    orElse: () => _recommendations.first,
  );
  return {
    'id': summary['id'],
    'symbol': summary['symbol'],
    'exchange': 'NSE',
    'companyName': summary['companyName'],
    'createdAt': _nowIso(),
    'updatedAt': _nowIso(),
    'asOf': _nowIso(),
    'entryPrice': summary['price'],
    'currentPrice': summary['price'],
    'targetPrice': summary['targetPrice'],
    'stopLoss': summary['stopLoss'],
    'horizonDays': 3,
    'expiryAt': null,
    'upsidePct': '4.8',
    'probability': '0.7',
    'score': '82',
    'confidence': '71',
    'trustScore': '65',
    'uncertainty': 'LOW',
    'evidenceStrength': 'STRONG',
    'fundamental': 'Fundamentals support the thesis.',
    'technical': 'Uptrend with support at the stop-loss.',
    'market': 'Market regime: risk-on.',
    'news': null,
    'events': null,
    'benchmarkRelative': null,
    'liquidity': 'HIGH',
    'providerEvidence': ['fundamental', 'technical', 'market'],
    'status': 'ISSUED',
    'predictionVersion': summary['predictionVersion'],
  };
}

final _history = [
  {
    'timestamp': _nowIso(),
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

final _events = [
  {
    'timestamp': _nowIso(),
    'eventType': 'NEWS',
    'description': 'Quarterly results beat estimates.',
    'materiality': 'HIGH',
  },
];

final _outcome = {
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

// Mutable so `PUT /preferences` round-trips within one server run, the
// same as a real backend would for a signed-in user.
Map<String, dynamic> _preferences = {
  'defaultHorizon': 3,
  'markets': ['IN'],
  'sectors': <String>[],
  'industries': <String>[],
  'marketCapBuckets': <String>[],
  'watchlist': <String>[],
  'notificationPreferences': {'mutedAlertTypes': <String>[]},
  'displayPreferences': {
    'themeMode': 'system',
    'showFreshnessTimestamps': true,
  },
  'riskPreference': null,
  'minConfidenceThreshold': null,
  'preferenceVersion': 'mock-1',
};

Future<void> _writeJson(
  HttpResponse response,
  int status,
  Map<String, dynamic> body,
) async {
  response.statusCode = status;
  response.headers.set(
    HttpHeaders.contentTypeHeader,
    'application/json; charset=utf-8',
  );
  // Permissive CORS: this is a localhost dev tool, not a deployed service.
  response.headers.set('Access-Control-Allow-Origin', '*');
  response.headers.set('Access-Control-Allow-Headers', '*');
  response.headers.set(
    'Access-Control-Allow-Methods',
    'GET, POST, PUT, OPTIONS',
  );
  response.write(jsonEncode(body));
  await response.close();
}

Future<Map<String, dynamic>> _readJsonBody(HttpRequest request) async {
  final raw = await utf8.decoder.bind(request).join();
  if (raw.isEmpty) return const {};
  return jsonDecode(raw) as Map<String, dynamic>;
}

Future<void> _handle(HttpRequest request) async {
  final path = request.uri.path;
  final method = request.method;
  // Silences the browser's CORS preflight for PUT/POST from a Flutter
  // web dev build.
  if (method == 'OPTIONS') {
    request.response.statusCode = 204;
    await request.response.close();
    return;
  }

  if (method == 'GET' && path == '/api/v1/app/bootstrap') {
    return _writeJson(
      request.response,
      200,
      _envelope({
        'apiVersion': 'v1',
        'contractVersion': _contractVersion,
        'serverTime': {'utc': _nowIso()},
        'capabilities': {
          'recommendations': true,
          'discovery': true,
          'marketSummary': true,
          'news': true,
          'events': true,
          'feedback': true,
          'preferences': true,
          'auth': true,
          'analytics': true,
        },
      }),
    );
  }

  if (method == 'POST' &&
      (path == '/api/v1/auth/login' || path == '/api/v1/auth/refresh')) {
    final body = await _readJsonBody(request);
    final userId = body['userId'] as String? ?? 'mock-user';
    return _writeJson(
      request.response,
      200,
      _envelope({
        'sessionToken': 'mock-session-token',
        'userId': userId,
        'issuedAt': _nowIso(),
        'expiresAt': DateTime.now()
            .toUtc()
            .add(const Duration(days: 1))
            .toIso8601String(),
      }),
    );
  }

  if (method == 'GET' && path == '/api/v1/auth/session') {
    return _writeJson(
      request.response,
      200,
      _envelope({
        'userId': 'mock-user',
        'sessionIssuedAt': _nowIso(),
        'sessionExpiresAt': DateTime.now()
            .toUtc()
            .add(const Duration(days: 1))
            .toIso8601String(),
        'requestId': 'mock-request-id',
      }),
    );
  }

  if (method == 'POST' && path == '/api/v1/auth/logout') {
    return _writeJson(request.response, 200, _envelope({'revoked': true}));
  }

  if (method == 'GET' && path == '/api/v1/recommendations') {
    return _writeJson(request.response, 200, _envelope(_recommendations));
  }

  final detailMatch = RegExp(
    r'^/api/v1/recommendations/(\d+)$',
  ).firstMatch(path);
  if (method == 'GET' && detailMatch != null) {
    final id = int.parse(detailMatch.group(1)!);
    return _writeJson(request.response, 200, _envelope(_detailFor(id)));
  }

  if (method == 'GET' &&
      RegExp(r'^/api/v1/recommendations/\d+/history$').hasMatch(path)) {
    return _writeJson(request.response, 200, _envelope(_history));
  }

  if (method == 'GET' &&
      RegExp(r'^/api/v1/recommendations/\d+/events$').hasMatch(path)) {
    return _writeJson(request.response, 200, _envelope(_events));
  }

  if (method == 'GET' &&
      RegExp(r'^/api/v1/recommendations/\d+/outcome$').hasMatch(path)) {
    return _writeJson(request.response, 200, _envelope(_outcome));
  }

  if (method == 'POST' &&
      RegExp(r'^/api/v1/recommendations/\d+/feedback$').hasMatch(path)) {
    return _writeJson(
      request.response,
      200,
      _envelope({
        'feedbackId': 'mock-feedback-${DateTime.now().microsecondsSinceEpoch}',
        'accepted': true,
        'recordedAt': _nowIso(),
        'learningImpact': 'queued',
      }),
    );
  }

  if (method == 'GET' && path == '/api/v1/preferences') {
    return _writeJson(request.response, 200, _envelope(_preferences));
  }

  if (method == 'PUT' && path == '/api/v1/preferences') {
    final body = await _readJsonBody(request);
    _preferences = {..._preferences, ...body};
    return _writeJson(request.response, 200, _envelope(_preferences));
  }

  if (method == 'GET' && path == '/api/v1/health') {
    return _writeJson(
      request.response,
      200,
      _envelope({
        'status': 'ok',
        'component': 'market-agent-m1',
        'apiVersion': 'v1',
      }),
    );
  }

  // Honest 404 in the real error envelope shape, not a bare HTTP 404 —
  // an unhandled route should look and behave like a real gap in the
  // contract, not a broken dev tool.
  return _writeJson(request.response, 404, {
    'error': {
      'code': 'MRA_NOT_FOUND',
      'message': 'No mock handler for $method $path.',
      'retryable': false,
    },
    'meta': {'requestId': 'mock-404', 'timestamp': _nowIso()},
  });
}

Future<void> main(List<String> args) async {
  final port = args.isNotEmpty ? int.parse(args.first) : 8090;
  final server = await HttpServer.bind(InternetAddress.anyIPv4, port);
  // ignore: avoid_print
  print(
    'Mock MRA API listening on http://localhost:$port '
    '(contractVersion=$_contractVersion) — Ctrl+C to stop.\n'
    'Run the app against it with:\n'
    '  flutter run --dart-define=API_BASE_URL=http://localhost:$port',
  );
  await for (final request in server) {
    // A malformed request body must return a mock 4xx, never crash the
    // dev server out from under whoever is using it.
    try {
      await _handle(request);
    } catch (e) {
      await _writeJson(request.response, 500, {
        'error': {
          'code': 'MRA_INTERNAL',
          'message': e.toString(),
          'retryable': true,
        },
        'meta': {'requestId': 'mock-500', 'timestamp': _nowIso()},
      });
    }
  }
}

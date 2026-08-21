import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/system/data_freshness_item.dart';
import 'package:mra_app/features/system/provider_status.dart';
import 'package:mra_app/features/system/system_event.dart';
import 'package:mra_app/features/system/system_health_screen.dart';
import 'package:mra_app/features/system/system_health_summary.dart';
import 'package:mra_app/features/system/system_repository.dart';

class _FakeSystemRepository extends SystemRepository {
  final SystemHealthSummary health;
  final List<ProviderStatus> providers;
  final List<DataFreshnessItem> freshness;
  final List<SystemEvent> firstPage;
  final List<SystemEvent> secondPage;
  final bool fail;

  _FakeSystemRepository({
    required this.health,
    this.providers = const [],
    this.freshness = const [],
    this.firstPage = const [],
    this.secondPage = const [],
    this.fail = false,
  });

  @override
  Future<SystemHealthSummary> fetchHealth() async {
    if (fail) throw Exception('boom');
    return health;
  }

  @override
  Future<List<ProviderStatus>> fetchProviders() async {
    if (fail) throw Exception('boom');
    return providers;
  }

  @override
  Future<List<DataFreshnessItem>> fetchDataFreshness() async {
    if (fail) throw Exception('boom');
    return freshness;
  }

  @override
  Future<SystemEventsPage> fetchEvents({
    String? cursor,
    int pageSize = 20,
  }) async {
    if (fail) throw Exception('boom');
    if (cursor == null) {
      return SystemEventsPage(
        items: firstPage,
        nextCursor: secondPage.isEmpty ? null : 'cursor-1',
      );
    }
    return SystemEventsPage(items: secondPage, nextCursor: null);
  }
}

final _okHealth = SystemHealthSummary(
  status: 'OK',
  checkedAt: DateTime.parse('2026-08-22T09:00:00Z'),
  apiVersion: 'v1',
  databaseOk: true,
  providerStatusCounts: const {'OK': 1},
  activeOutageCount: 0,
  marketSession: 'MARKET_HOURS',
);

final _degradedHealth = SystemHealthSummary(
  status: 'DEGRADED',
  checkedAt: DateTime.parse('2026-08-22T09:00:00Z'),
  apiVersion: 'v1',
  databaseOk: true,
  providerStatusCounts: const {'WEAK': 1},
  activeOutageCount: 1,
  marketSession: 'CLOSED',
);

final _provider = ProviderStatus(
  providerId: 'yahoo-finance',
  capability: 'MARKET_DATA',
  status: 'OK',
  lastSuccessAt: DateTime.parse('2026-08-22T08:00:00Z'),
  latencyMs: 1200,
  freshness: const Freshness(
    ageSeconds: 60,
    thresholdSeconds: 86400,
    isFresh: true,
  ),
  failureRate: 0.0,
  fallbackActive: false,
  qualityScore: 0.98,
);

final _freshnessItem = DataFreshnessItem(
  capability: 'MARKET_DATA',
  lastSuccessAt: DateTime.parse('2026-08-22T08:00:00Z'),
  ageSeconds: 60,
  thresholdSeconds: 86400,
  isFresh: true,
);

final _event1 = SystemEvent(
  id: 'outage-1',
  type: 'PROVIDER_OUTAGE',
  severity: 'PARTIAL',
  capability: 'MARKET_DATA',
  exchange: null,
  description: '1/2 provider(s) degraded for MARKET_DATA: yahoo-finance',
  occurredAt: DateTime.parse('2026-08-22T07:00:00Z'),
);

final _event2 = SystemEvent(
  id: 'closure-1',
  type: 'MARKET_UNEXPECTED_CLOSURE',
  severity: 'INFO',
  capability: null,
  exchange: 'NSE',
  description: 'Unexpected closure on 2026-08-21: test',
  occurredAt: DateTime.parse('2026-08-21T07:00:00Z'),
);

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets(
    'shows overall status, market session and an empty provider/events state',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          SystemHealthScreen(
            repository: _FakeSystemRepository(health: _okHealth),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('System & provider health'), findsOneWidget);
      expect(find.text('OK'), findsOneWidget);
      expect(find.textContaining('Market: Open'), findsOneWidget);
      expect(find.textContaining('No provider activity'), findsOneWidget);
      expect(find.textContaining('No provider outages'), findsOneWidget);
    },
  );

  testWidgets('shows degraded status with active outage count', (tester) async {
    await tester.pumpWidget(
      _wrap(
        SystemHealthScreen(
          repository: _FakeSystemRepository(health: _degradedHealth),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('DEGRADED'), findsOneWidget);
    expect(find.textContaining('1 active outage(s)'), findsOneWidget);
    expect(find.textContaining('Market: Closed'), findsOneWidget);
  });

  testWidgets('lists provider grid rows and freshness by capability', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        SystemHealthScreen(
          repository: _FakeSystemRepository(
            health: _okHealth,
            providers: [_provider],
            freshness: [_freshnessItem],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('yahoo-finance'), findsWidgets);
    expect(find.text('1200 ms'), findsOneWidget);
    expect(find.text('98%'), findsOneWidget);
    expect(find.text('MARKET_DATA'), findsWidgets);
  });

  testWidgets('load more fetches and appends the next page of events', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        SystemHealthScreen(
          repository: _FakeSystemRepository(
            health: _okHealth,
            firstPage: [_event1],
            secondPage: [_event2],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Load more'), findsOneWidget);
    expect(find.textContaining('Unexpected closure'), findsNothing);

    await tester.ensureVisible(find.text('Load more'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Unexpected closure'), findsOneWidget);
    expect(find.text('Load more'), findsNothing);
  });

  testWidgets('a failed fetch shows a retry state, not a crash', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        SystemHealthScreen(
          repository: _FakeSystemRepository(health: _okHealth, fail: true),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Retry'), findsOneWidget);
  });
}

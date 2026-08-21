import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/detail/event_item.dart';
import 'package:mra_app/features/detail/history_item.dart';
import 'package:mra_app/features/detail/recommendation_detail.dart';
import 'package:mra_app/features/detail/recommendation_detail_repository.dart';
import 'package:mra_app/features/detail/recommendation_detail_screen.dart';
import 'package:mra_app/features/detail/recommendation_outcome.dart';

RecommendationDetail _detail({
  double? trustScore = 65,
  String? benchmarkRelative,
}) {
  return RecommendationDetail.fromJson({
    'id': 1,
    'symbol': 'TATASTEEL',
    'exchange': 'NSE',
    'companyName': 'Tata Steel Ltd.',
    'predictionVersion': {
      'modelVersion': '1',
      'featureVersion': '1',
      'consensusContractVersion': '1',
      'horizonSelectionVersion': '1',
      'scoringContractVersion': '1',
      'rankingVersion': '1',
    },
    'createdAt': '2026-08-01T09:00:00Z',
    'updatedAt': '2026-08-21T09:00:00Z',
    'asOf': '2026-08-21T09:00:00Z',
    'entryPrice': '160.00',
    'currentPrice': '168.35',
    'targetPrice': '176.50',
    'stopLoss': '163.00',
    'horizonDays': 3,
    'expiryAt': null,
    'upsidePct': '4.8',
    'probability': '0.7',
    'score': '82',
    'confidence': '71',
    'trustScore': trustScore?.toString(),
    'uncertainty': 'LOW',
    'evidenceStrength': 'STRONG',
    'fundamental': 'Revenue growth 8% YoY.',
    'technical': 'Above 50-day moving average.',
    'market': 'NSE steel sector up 1.2%.',
    'news': null,
    'events': null,
    'benchmarkRelative': benchmarkRelative,
    'liquidity': 'HIGH',
    'providerEvidence': ['yahoo_finance'],
    'status': 'ISSUED',
  });
}

RecommendationHistoryItem _historyItem({int version = 1}) {
  return RecommendationHistoryItem.fromJson({
    'timestamp': '2026-08-1${version}T09:00:00Z',
    'version': version,
    'price': '165.00',
    'targetPrice': '176.50',
    'stopLoss': '163.00',
    'probability': '0.7',
    'score': '80',
    'confidence': '70',
    'trustScore': '60',
    'triggerType': 'REVISION',
    'triggerEventId': null,
    'changeSummary': 'Target raised from 170 to 176.50.',
  });
}

RecommendationEventItem _eventItem() {
  return RecommendationEventItem.fromJson({
    'timestamp': '2026-08-15T09:00:00Z',
    'eventType': 'NEWS',
    'description': 'Company announces new plant.',
    'materiality': 'HIGH',
  });
}

RecommendationOutcome _pendingOutcome() {
  return RecommendationOutcome.fromJson({
    'status': 'PENDING',
    'detectedAt': null,
    'observedPrice': null,
    'realizedReturnPct': null,
    'targetHit': null,
    'stopLossHit': null,
    'horizonExpired': null,
    'benchmarkReturnPct': null,
    'evidenceId': null,
  });
}

RecommendationOutcome _targetHitOutcome() {
  return RecommendationOutcome.fromJson({
    'status': 'EVALUATED',
    'detectedAt': '2026-08-20T09:00:00Z',
    'observedPrice': '177.00',
    'realizedReturnPct': '5.2',
    'targetHit': true,
    'stopLossHit': false,
    'horizonExpired': false,
    'benchmarkReturnPct': null,
    'evidenceId': 99,
  });
}

class _FakeDetailRepository extends RecommendationDetailRepository {
  final RecommendationDetail Function()? onDetail;
  final List<RecommendationHistoryItem> history;
  final List<RecommendationEventItem> events;
  final RecommendationOutcome Function()? onOutcome;

  _FakeDetailRepository({
    this.onDetail,
    this.history = const [],
    this.events = const [],
    this.onOutcome,
  });

  @override
  Future<RecommendationDetail> fetchDetail(int id) async {
    if (onDetail == null) {
      throw const ApiException(code: 'MRA_NOT_FOUND', message: 'Not found');
    }
    return onDetail!();
  }

  @override
  Future<HistoryPage> fetchHistory(
    int id, {
    DateTime? from,
    DateTime? to,
    String? cursor,
    int pageSize = 20,
  }) async => HistoryPage(items: history, nextCursor: null);

  @override
  Future<EventsPage> fetchEvents(
    int id, {
    String? cursor,
    int pageSize = 20,
  }) async => EventsPage(items: events, nextCursor: null);

  @override
  Future<RecommendationOutcome> fetchOutcome(int id) async {
    return (onOutcome ?? _pendingOutcome)();
  }
}

Widget _wrap(Widget child) {
  return MaterialApp(theme: MraTheme.light(), home: child);
}

void main() {
  testWidgets('renders header, metrics and pending outcome', (tester) async {
    final repo = _FakeDetailRepository(onDetail: _detail);
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsWidgets);
    expect(find.text('Tata Steel Ltd.'), findsOneWidget);
    expect(find.textContaining('Not evaluated yet'), findsOneWidget);
    expect(
      find.text('Benchmark-relative result not available yet.'),
      findsOneWidget,
    );
  });

  testWidgets('shows explicit N/A trust when trust score is null', (
    tester,
  ) async {
    final repo = _FakeDetailRepository(
      onDetail: () => _detail(trustScore: null),
    );
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('N/A'), findsOneWidget);
  });

  testWidgets('renders revision timeline and events from history/events', (
    tester,
  ) async {
    final repo = _FakeDetailRepository(
      onDetail: _detail,
      history: [_historyItem()],
      events: [_eventItem()],
    );
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Target raised from 170'), findsOneWidget);
    expect(find.text('Company announces new plant.'), findsOneWidget);
  });

  testWidgets('renders target-hit outcome chip when evaluated', (tester) async {
    final repo = _FakeDetailRepository(
      onDetail: _detail,
      onOutcome: _targetHitOutcome,
    );
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Target hit'), findsOneWidget);
    expect(find.text('5.2% realized'), findsOneWidget);
  });

  testWidgets('shows an error state with retry when the fetch fails', (
    tester,
  ) async {
    final repo = _FakeDetailRepository();
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Not found'), findsOneWidget);
  });
}
